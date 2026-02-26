import io
import json
import logging
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings as app_settings
from app.database import get_db
from app.models import (
    BackupJob,
    NotificationChannel,
    RetentionPolicy,
    Schedule,
    Setting,
    StorageBackend,
)
from app.schemas import SettingsBundle

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user)])

# Default settings values
DEFAULTS: dict[str, Any] = {
    "instance_name": "Backup Buddy",
    "timezone": "utc",
    "maintenance_mode": False,
    "rclone_enabled": False,
    "rclone_binary": "/usr/bin/rclone",
    "rclone_config": "/root/.config/rclone/rclone.conf",
    "rclone_flags": "",
    "rclone_config_text": "",
    "default_compression": "gzip",
    "default_encryption": "none",
    "verify_backups": True,
    "parallel_uploads": True,
    "notify_on_success": False,
    "notify_on_warning": True,
    "notify_on_failure": True,
    "log_retention_backup_days": 30,
    "log_retention_system_days": 14,
    "syslog_enabled": False,
    "syslog_host": "",
    "syslog_port": 514,
    "syslog_protocol": "udp",
    "syslog_facility": "local0",
}


@router.get("", response_model=SettingsBundle)
def get_settings(db: Session = Depends(get_db)):
    rows = db.query(Setting).all()
    result = dict(DEFAULTS)
    for row in rows:
        try:
            result[row.key] = json.loads(row.value) if row.value is not None else None
        except (json.JSONDecodeError, TypeError):
            result[row.key] = row.value
    return SettingsBundle(settings=result)


@router.put("")
def update_settings(bundle: SettingsBundle, db: Session = Depends(get_db)):
    for key, value in bundle.settings.items():
        existing = db.query(Setting).get(key)
        serialized = json.dumps(value)
        if existing:
            existing.value = serialized
        else:
            db.add(Setting(key=key, value=serialized))
    db.commit()

    # If the rclone inline config was provided, write it to the config file
    _sync_rclone_config(bundle.settings)

    # Reconfigure syslog if settings changed
    from app.syslog_handler import configure_syslog
    configure_syslog(bundle.settings)

    return get_settings(db)


def _sync_rclone_config(settings_dict: dict[str, Any]) -> None:
    """Write the rclone_config_inline text to the rclone config file on disk."""
    config_text = settings_dict.get("rclone_config_inline") or settings_dict.get("rclone_config_text") or ""
    if not isinstance(config_text, str) or not config_text.strip():
        return

    config_path = Path(
        settings_dict.get("rclone_config_path")
        or app_settings.RCLONE_CONFIG
    )
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(config_text.strip() + "\n")
        logger.info("Rclone config written to %s (%d bytes)", config_path, len(config_text))
    except Exception as exc:
        logger.error("Failed to write rclone config to %s: %s", config_path, exc)


@router.post("/reset")
def reset_settings(db: Session = Depends(get_db)):
    """Reset all settings to defaults."""
    db.query(Setting).delete(synchronize_session=False)
    db.commit()
    return get_settings(db)


@router.get("/export")
def export_config(db: Session = Depends(get_db)):
    """Export all configuration as a downloadable .zip containing JSON files."""

    def _rows_to_dicts(rows, columns):
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

    # Collect all config tables
    settings_rows = db.query(Setting).all()
    settings_dict = {}
    for row in settings_rows:
        try:
            settings_dict[row.key] = json.loads(row.value) if row.value is not None else None
        except (json.JSONDecodeError, TypeError):
            settings_dict[row.key] = row.value

    storages = _rows_to_dicts(
        db.query(StorageBackend).all(),
        ["id", "name", "type", "config_json", "created_at", "updated_at"],
    )

    schedules = _rows_to_dicts(
        db.query(Schedule).all(),
        ["id", "name", "cron", "description", "enabled", "created_at", "updated_at"],
    )

    retention_policies = _rows_to_dicts(
        db.query(RetentionPolicy).all(),
        ["id", "name", "description", "retention_days", "min_backups", "max_backups", "created_at", "updated_at"],
    )

    jobs = _rows_to_dicts(
        db.query(BackupJob).all(),
        ["id", "name", "storage_id", "schedule_id", "retention_id", "enabled", "created_at", "updated_at"],
    )

    notifications = _rows_to_dicts(
        db.query(NotificationChannel).all(),
        ["id", "name", "type", "config_json", "events_json", "enabled", "created_at", "updated_at"],
    )

    # Build zip in memory
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("settings.json", json.dumps(settings_dict, indent=2))
        zf.writestr("storage_backends.json", json.dumps(storages, indent=2))
        zf.writestr("schedules.json", json.dumps(schedules, indent=2))
        zf.writestr("retention_policies.json", json.dumps(retention_policies, indent=2))
        zf.writestr("backup_jobs.json", json.dumps(jobs, indent=2))
        zf.writestr("notification_channels.json", json.dumps(notifications, indent=2))
        zf.writestr(
            "metadata.json",
            json.dumps(
                {
                    "app_version": app_settings.APP_VERSION,
                    "exported_at": datetime.now(timezone.utc).isoformat(),
                },
                indent=2,
            ),
        )
    buf.seek(0)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"backup_buddy_config_{timestamp}.zip"

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import")
def import_config(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Import configuration from a previously exported .zip file.

    The zip is expected to contain JSON files produced by the /export endpoint.
    Existing rows in each table are replaced (upsert by primary key).
    Foreign-key dependent tables (backup_jobs) are loaded last so that
    referenced schedules / storages / retention policies already exist.
    """
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="File must be a .zip archive")

    try:
        raw = file.file.read()
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid or corrupted zip file")

    def _read_json(name: str):
        """Read and parse a JSON file from the zip, returning None if missing."""
        try:
            return json.loads(zf.read(name))
        except KeyError:
            return None
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail=f"Invalid JSON in {name}")

    imported: dict[str, int] = {}

    # ── 1. Settings (key-value) ────────────────────────────────────────────
    settings_dict = _read_json("settings.json")
    if settings_dict and isinstance(settings_dict, dict):
        for key, value in settings_dict.items():
            existing = db.query(Setting).get(key)
            serialized = json.dumps(value)
            if existing:
                existing.value = serialized
            else:
                db.add(Setting(key=key, value=serialized))
        imported["settings"] = len(settings_dict)

    # ── 2. Storage Backends ────────────────────────────────────────────────
    storages_list = _read_json("storage_backends.json")
    if storages_list and isinstance(storages_list, list):
        for item in storages_list:
            row = db.query(StorageBackend).get(item["id"])
            if row:
                row.name = item["name"]
                row.type = item["type"]
                row.config_json = item.get("config_json", "{}")
            else:
                db.add(StorageBackend(
                    id=item["id"], name=item["name"], type=item["type"],
                    config_json=item.get("config_json", "{}"),
                ))
        imported["storage_backends"] = len(storages_list)

    # ── 3. Schedules ──────────────────────────────────────────────────────
    schedules_list = _read_json("schedules.json")
    if schedules_list and isinstance(schedules_list, list):
        for item in schedules_list:
            row = db.query(Schedule).get(item["id"])
            if row:
                row.name = item["name"]
                row.cron = item["cron"]
                row.description = item.get("description")
                row.enabled = item.get("enabled", True)
            else:
                db.add(Schedule(
                    id=item["id"], name=item["name"], cron=item["cron"],
                    description=item.get("description"),
                    enabled=item.get("enabled", True),
                ))
        imported["schedules"] = len(schedules_list)

    # ── 4. Retention Policies ─────────────────────────────────────────────
    retention_list = _read_json("retention_policies.json")
    if retention_list and isinstance(retention_list, list):
        for item in retention_list:
            row = db.query(RetentionPolicy).get(item["id"])
            if row:
                row.name = item["name"]
                row.description = item.get("description")
                row.retention_days = item["retention_days"]
                row.min_backups = item.get("min_backups", 1)
                row.max_backups = item.get("max_backups")
            else:
                db.add(RetentionPolicy(
                    id=item["id"], name=item["name"],
                    description=item.get("description"),
                    retention_days=item["retention_days"],
                    min_backups=item.get("min_backups", 1),
                    max_backups=item.get("max_backups"),
                ))
        imported["retention_policies"] = len(retention_list)

    # Flush so FK references resolve for backup_jobs
    db.flush()

    # ── 5. Notification Channels ──────────────────────────────────────────
    notif_list = _read_json("notification_channels.json")
    if notif_list and isinstance(notif_list, list):
        for item in notif_list:
            row = db.query(NotificationChannel).get(item["id"])
            if row:
                row.name = item["name"]
                row.type = item["type"]
                row.config_json = item.get("config_json", "{}")
                row.events_json = item.get("events_json", "[]")
                row.enabled = item.get("enabled", True)
            else:
                db.add(NotificationChannel(
                    id=item["id"], name=item["name"], type=item["type"],
                    config_json=item.get("config_json", "{}"),
                    events_json=item.get("events_json", "[]"),
                    enabled=item.get("enabled", True),
                ))
        imported["notification_channels"] = len(notif_list)

    # ── 6. Backup Jobs (depends on storages, schedules, retention) ────────
    jobs_list = _read_json("backup_jobs.json")
    if jobs_list and isinstance(jobs_list, list):
        for item in jobs_list:
            row = db.query(BackupJob).get(item["id"])
            if row:
                row.name = item["name"]
                row.storage_id = item["storage_id"]
                row.schedule_id = item.get("schedule_id")
                row.retention_id = item.get("retention_id")
                row.enabled = item.get("enabled", True)
            else:
                db.add(BackupJob(
                    id=item["id"], name=item["name"],
                    storage_id=item["storage_id"],
                    schedule_id=item.get("schedule_id"),
                    retention_id=item.get("retention_id"),
                    enabled=item.get("enabled", True),
                ))
        imported["backup_jobs"] = len(jobs_list)

    db.commit()

    # Sync rclone config to disk if it was part of the import
    if settings_dict:
        _sync_rclone_config(settings_dict)

    logger.info("Config imported: %s", imported)
    return {"status": "ok", "imported": imported}
