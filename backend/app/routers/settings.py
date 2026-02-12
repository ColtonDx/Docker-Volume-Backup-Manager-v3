import json
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Setting
from app.schemas import SettingsBundle

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
    return get_settings(db)


@router.post("/reset")
def reset_settings(db: Session = Depends(get_db)):
    """Reset all settings to defaults."""
    db.query(Setting).delete(synchronize_session=False)
    db.commit()
    return get_settings(db)
