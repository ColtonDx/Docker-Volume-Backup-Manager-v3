"""DVBM Configuration Backup Service.

Exports the application configuration (same payload as /api/settings/export)
and uploads it to a configured storage backend on a cron schedule.
Old files are pruned to keep only the N most recent.
"""

from __future__ import annotations

import io
import json
import logging
import os
import tempfile
import zipfile
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

        keep_count = int(settings_map.get("config_backup_keep_count", 5))
        notification_id = settings_map.get("config_backup_notification_id")

        storage = db.query(StorageBackend).get(int(storage_id))
        if not storage:
            msg = f"Config backup failed: storage backend ID {storage_id} not found"
            logger.error(msg)
            self._log(db, "error", msg)
            self._notify(db, notification_id, "failure", msg)
            return

        config = json.loads(storage.config_json or "{}")

        # Generate the config zip in memory
        try:
            zip_bytes = self._generate_config_zip(db)
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

        # Apply retention: keep only the N most recent config backup files
        if keep_count > 0:
            try:
                files = storage_service.list_files(storage.type, config, prefix=CONFIG_BACKUP_PREFIX)
                # Filenames are timestamp-based so alphabetical order == chronological order
                sorted_files = sorted(files, key=lambda f: f["name"])
                to_delete = sorted_files[:-keep_count] if len(sorted_files) > keep_count else []
                for f in to_delete:
                    try:
                        storage_service.delete_remote(storage.type, config, f["path"])
                        logger.info("Config backup retention: deleted %s", f["path"])
                    except Exception as exc:
                        logger.warning("Config backup retention: failed to delete %s: %s", f["path"], exc)
            except Exception as exc:
                logger.warning("Config backup retention check failed: %s", exc)

        msg = f"Config backup completed: {filename}"
        self._log(db, "success", msg)
        self._notify(db, notification_id, "success", msg)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _load_settings(self, db) -> dict:
        from app.models import Setting

        result: dict = {}
        for row in db.query(Setting).all():
            try:
                result[row.key] = json.loads(row.value) if row.value is not None else None
            except (json.JSONDecodeError, TypeError):
                result[row.key] = row.value
        return result

    def _generate_config_zip(self, db) -> bytes:
        """Produce the same export zip as the /api/settings/export endpoint."""
        from app.config import settings as app_settings
        from app.models import (
            BackupJob,
            NotificationChannel,
            RetentionPolicy,
            Schedule,
            Setting,
            StorageBackend,
        )

        def rows_to_dicts(rows, columns):
            out = []
            for r in rows:
                d = {}
                for c in columns:
                    val = getattr(r, c, None)
                    if isinstance(val, datetime):
                        val = val.isoformat()
                    d[c] = val
                out.append(d)
            return out

        settings_dict: dict = {}
        for row in db.query(Setting).all():
            try:
                settings_dict[row.key] = json.loads(row.value) if row.value is not None else None
            except (json.JSONDecodeError, TypeError):
                settings_dict[row.key] = row.value

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("settings.json", json.dumps(settings_dict, indent=2))
            zf.writestr("storage_backends.json", json.dumps(rows_to_dicts(
                db.query(StorageBackend).all(),
                ["id", "name", "type", "config_json", "created_at", "updated_at"],
            ), indent=2))
            zf.writestr("schedules.json", json.dumps(rows_to_dicts(
                db.query(Schedule).all(),
                ["id", "name", "cron", "description", "enabled", "created_at", "updated_at"],
            ), indent=2))
            zf.writestr("retention_policies.json", json.dumps(rows_to_dicts(
                db.query(RetentionPolicy).all(),
                ["id", "name", "description", "retention_days", "min_backups", "max_backups", "created_at", "updated_at"],
            ), indent=2))
            zf.writestr("backup_jobs.json", json.dumps(rows_to_dicts(
                db.query(BackupJob).all(),
                ["id", "name", "label_key", "label_value", "storage_id", "schedule_id", "retention_id", "enabled", "created_at", "updated_at"],
            ), indent=2))
            zf.writestr("notification_channels.json", json.dumps(rows_to_dicts(
                db.query(NotificationChannel).all(),
                ["id", "name", "type", "config_json", "events_json", "enabled", "created_at", "updated_at"],
            ), indent=2))
            zf.writestr("metadata.json", json.dumps({
                "app_version": app_settings.APP_VERSION,
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "type": "automated_config_backup",
            }, indent=2))
        buf.seek(0)
        return buf.read()

    def _log(self, db, level: str, message: str) -> None:
        from app.models import LogEntry

        db.add(LogEntry(level=level, job_name="DVBM Config Backup", message=message))
        db.commit()

    def _notify(self, db, notification_id: int | None, event: str, message: str) -> None:
        if not notification_id:
            return
        from app.models import NotificationChannel
        from app.services.notification_service import notification_service

        channel = db.query(NotificationChannel).get(int(notification_id))
        if not channel or not channel.enabled:
            return
        config = json.loads(channel.config_json or "{}")
        try:
            notification_service._send(channel.type, config, "DVBM Config Backup", event, message)
        except Exception as exc:
            logger.warning("Config backup notification failed: %s", exc)


config_backup_service = ConfigBackupService()
