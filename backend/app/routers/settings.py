import io
import json
import logging
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
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
