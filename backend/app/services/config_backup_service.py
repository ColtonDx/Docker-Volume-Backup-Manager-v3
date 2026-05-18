"""DVBM Configuration Backup Service.

Exports the application configuration (same payload as /api/settings/export)
and uploads it to a configured storage backend on a cron schedule.
Old files are pruned to keep only the N most recent.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

CONFIG_BACKUP_PREFIX = "dvbm_config_"


class ConfigBackupService:
    def run(self) -> None:
        """Run the config backup. Invoked by APScheduler or the manual trigger endpoint."""
        from app.database import SessionLocal

        with SessionLocal() as db:
            self._do_backup(db)

    # ------------------------------------------------------------------
    # Core backup logic
    # ------------------------------------------------------------------

    def _do_backup(self, db) -> None:
        from app.models import LogEntry, NotificationChannel, Setting, StorageBackend
        from app.services.storage_service import storage_service

        settings_map = self._load_settings(db)

        enabled = settings_map.get("config_backup_enabled", False)
        if not enabled:
            return

        storage_id = settings_map.get("config_backup_storage_id")
        if not storage_id:
            logger.warning("Config backup is enabled but no storage backend is configured")
            return

        retention_id = settings_map.get("config_backup_retention_id")
        notification_id = settings_map.get("config_backup_notification_id")

        storage = db.get(StorageBackend, int(storage_id))
        if not storage:
            msg = f"Config backup failed: storage backend ID {storage_id} not found"
            logger.error(msg)
            self._log(db, "error", msg)
            self._notify(db, notification_id, "failure", msg)
            return

        config = json.loads(storage.config_json or "{}")

        # Generate the config zip in memory
        try:
            from app.config_export import build_config_zip
            zip_bytes = build_config_zip(db, backup_type="automated_config_backup")
        except Exception as exc:
            msg = f"Config backup failed: could not generate export zip: {exc}"
            logger.error(msg)
            self._log(db, "error", msg)
            self._notify(db, notification_id, "failure", msg)
            return

        # Write to a temp file then upload
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{CONFIG_BACKUP_PREFIX}{timestamp}.zip"
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                tmp.write(zip_bytes)
                tmp_path = tmp.name

            storage_service.upload(storage.type, config, tmp_path, filename)
            logger.info("Config backup uploaded: %s to storage '%s'", filename, storage.name)
        except Exception as exc:
            msg = f"Config backup upload failed: {exc}"
            logger.error(msg)
            self._log(db, "error", msg)
            self._notify(db, notification_id, "failure", msg)
            return
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        # Apply retention policy if one is configured
        if retention_id:
            try:
                from app.models import RetentionPolicy
                policy = db.get(RetentionPolicy, int(retention_id))
                if policy:
                    self._apply_retention(db, storage, config, policy)
            except Exception as exc:
                logger.warning("Config backup retention failed: %s", exc)

        msg = f"Config backup completed: {filename}"
        self._log(db, "success", msg)
        self._notify(db, notification_id, "success", msg)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _apply_retention(self, db, storage, config: dict, policy) -> None:
        """Delete config backup files from storage according to the retention policy."""
        from app.services.storage_service import storage_service

        files = storage_service.list_files(storage.type, config, prefix=CONFIG_BACKUP_PREFIX, suffix=".zip")
        # Filenames are timestamp-based so alphabetical == chronological
        sorted_files = sorted(files, key=lambda f: f["name"])

        to_delete: list[dict] = []

        # Age-based: mark files older than retention_days for deletion
        if policy.retention_days and policy.retention_days > 0:
            cutoff = datetime.now(timezone.utc).timestamp() - policy.retention_days * 86400
            for f in sorted_files:
                # Fall back to filename-based date parsing if mtime not available
                mtime = f.get("mtime")
                if mtime is not None:
                    if mtime < cutoff:
                        to_delete.append(f)
                else:
                    try:
                        # filename: dvbm_config_YYYYMMDD_HHmmss.zip
                        ts_part = f["name"].replace(CONFIG_BACKUP_PREFIX, "").replace(".zip", "")
                        dt = datetime.strptime(ts_part, "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
                        if dt.timestamp() < cutoff:
                            to_delete.append(f)
                    except Exception:
                        pass

        # Count-based: also enforce max_backups
        if policy.max_backups and policy.max_backups > 0:
            remaining = [f for f in sorted_files if f not in to_delete]
            excess = len(remaining) - policy.max_backups
            if excess > 0:
                to_delete.extend(remaining[:excess])

        # Respect min_backups: don't delete below the floor
        min_keep = policy.min_backups or 1
        would_survive = [f for f in sorted_files if f not in to_delete]
        while len(would_survive) < min_keep and to_delete:
            to_delete.pop()
            would_survive = [f for f in sorted_files if f not in to_delete]

        for f in to_delete:
            try:
                storage_service.delete_remote(storage.type, config, f["path"])
                logger.info("Config backup retention: deleted %s", f["path"])
            except Exception as exc:
                logger.warning("Config backup retention: failed to delete %s: %s", f["path"], exc)

    def _load_settings(self, db) -> dict:
        from app.models import Setting

        result: dict = {}
        for row in db.query(Setting).all():
            try:
                result[row.key] = json.loads(row.value) if row.value is not None else None
            except (json.JSONDecodeError, TypeError):
                result[row.key] = row.value
        return result

    def _log(self, db, level: str, message: str) -> None:
        from app.models import LogEntry

        db.add(LogEntry(level=level, job_name="DVBM Config Backup", message=message))
        db.commit()

    def _notify(self, db, notification_id: int | None, event: str, message: str) -> None:
        if not notification_id:
            return
        from app.models import NotificationChannel
        from app.services.notification_service import notification_service

        channel = db.get(NotificationChannel, int(notification_id))
        if not channel or not channel.enabled:
            return
        subscribed = json.loads(channel.events_json or "[]")
        if event not in subscribed:
            return
        config = json.loads(channel.config_json or "{}")
        try:
            notification_service._send(channel.type, config, "DVBM Config Backup", event, message)
        except Exception as exc:
            logger.warning("Config backup notification failed: %s", exc)


config_backup_service = ConfigBackupService()
