"""Shared configuration export logic.

Produces the same zip structure as the /api/settings/export endpoint and the
automated config backup service. Import this module from both rather than
duplicating the query and zip-building code.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone


def build_config_zip(db, backup_type: str | None = None) -> bytes:
    """Build a configuration export zip and return its raw bytes.

    Args:
        db: SQLAlchemy session.
        backup_type: Optional value written to metadata.json as "type".
                     Omit (None) for manual exports; pass "automated_config_backup"
                     for scheduled config backup files.
    """
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

    metadata: dict = {
        "app_version": app_settings.APP_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }
    if backup_type is not None:
        metadata["type"] = backup_type

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
        zf.writestr("metadata.json", json.dumps(metadata, indent=2))
    buf.seek(0)
    return buf.read()
