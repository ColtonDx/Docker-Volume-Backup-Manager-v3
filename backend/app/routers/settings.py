import io
import json
import logging
import zipfile
from datetime import datetime, timezone
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
from app.services import rclone_config

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user)])

# Default settings values
DEFAULTS: dict[str, Any] = {
    "timezone": "UTC",
    "default_label_key": "dvbm.job",
    "rclone_enabled": False,
    "rclone_binary": "/usr/bin/rclone",
    "rclone_config": "/root/.config/rclone/rclone.conf",
    "rclone_flags": "",
    "rclone_config_text": "",
    "default_compression": "gzip",
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
    # Automated config backup
    "config_backup_enabled": False,
    "config_backup_storage_id": None,
    "config_backup_schedule_id": None,
    "config_backup_notification_id": None,
    "config_backup_retention_id": None,
}


def _decode_setting(value: Any) -> Any:
    """Decode a stored setting value (JSON-encoded, with a raw-string fallback)."""
    if value is None:
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


@router.get("", response_model=SettingsBundle)
def get_settings(db: Session = Depends(get_db)):
    rows = db.query(Setting).all()
    result = dict(DEFAULTS)
    for row in rows:
        result[row.key] = _decode_setting(row.value)
    # Instance name is always derived from the APP_NAME env var (read-only)
    result["instance_name"] = app_settings.APP_NAME
    from app.secrets_mask import mask_config
    return SettingsBundle(settings=mask_config(result))


@router.get("/rclone/status")
def rclone_status(db: Session = Depends(get_db)):
    """Where the rclone config comes from and which remotes it defines.

    Never returns the config file contents or any secret values.
    """
    stored = {row.key: _decode_setting(row.value) for row in db.query(Setting).all()}
    return rclone_config.get_status(stored)


@router.put("")
def update_settings(bundle: SettingsBundle, db: Session = Depends(get_db)):
    # Preserve secret settings left at the masking sentinel (unchanged) rather
    # than overwriting the stored value with the sentinel itself.
    from app.secrets_mask import unmask_config
    stored = {row.key: _decode_setting(row.value) for row in db.query(Setting).all()}
    incoming = unmask_config(bundle.settings, stored)

    # Refuse to replace a hand-managed (e.g. mounted) rclone config unless the
    # caller explicitly confirmed. Checked before anything is saved.
    new_text = rclone_config.config_text_from(incoming)
    config_path = rclone_config.config_path_from(incoming)
    plan = "skip"
    if new_text:
        plan = rclone_config.plan_write(config_path, new_text, rclone_config.config_text_from(stored))
        if plan == "confirm" and not bundle.overwrite_rclone_config:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"An rclone config file already exists at {config_path} and was not "
                    "written by Settings. Confirm to overwrite it."
                ),
            )

    for key, value in incoming.items():
        existing = db.get(Setting, key)
        serialized = json.dumps(value)
        if existing:
            existing.value = serialized
        else:
            db.add(Setting(key=key, value=serialized))
    db.commit()

    # If the rclone inline config was provided, write it to the config file
    if plan in ("write", "confirm"):
        rclone_config.write_config(config_path, new_text)
    elif new_text:
        logger.info("Rclone config at %s left unchanged (saved text not applied)", config_path)

    # Reconfigure syslog if settings changed
    from app.syslog_handler import configure_syslog
    configure_syslog(incoming)

    # Reconfigure scheduler timezone if it changed
    try:
        new_tz = incoming.get("timezone")
        from app.services.scheduler_service import scheduler_service
        if new_tz and isinstance(new_tz, str) and new_tz.strip():
            scheduler_service.reconfigure_timezone(new_tz.strip())
        else:
            scheduler_service.sync_jobs()
    except Exception as exc:
        logger.warning("Scheduler sync after settings save failed: %s", exc)

    return get_settings(db)


@router.post("/reset")
def reset_settings(db: Session = Depends(get_db)):
    """Reset all settings to defaults."""
    db.query(Setting).delete(synchronize_session=False)
    db.commit()
    from app.services.scheduler_service import scheduler_service
    scheduler_service.sync_jobs()
    return get_settings(db)


@router.post("/config-backup/run")
def run_config_backup_now():
    """Manually trigger a config backup immediately."""
    import threading

    from app.services.config_backup_service import config_backup_service

    thread = threading.Thread(target=config_backup_service.run, daemon=True)
    thread.start()
    return {"message": "Config backup started"}


@router.get("/export")
def export_config(db: Session = Depends(get_db)):
    """Export all configuration as a downloadable .zip containing JSON files."""
    from app.config_export import build_config_zip

    zip_bytes = build_config_zip(db)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"dvbm_config_{timestamp}.zip"

    return StreamingResponse(
        io.BytesIO(zip_bytes),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import")
def import_config(
    file: UploadFile = File(...),
    overwrite_rclone_config: bool = False,
    db: Session = Depends(get_db),
):
    """Import configuration from a previously exported .zip file.

    The zip is expected to contain JSON files produced by the /export endpoint.
    Existing rows in each table are replaced (upsert by primary key).
    Foreign-key dependent tables (backup_jobs) are loaded last so that
    referenced schedules / storages / retention policies already exist.
    """
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="File must be a .zip archive")

    # Bounds to prevent memory exhaustion / zip bombs. Config exports are tiny
    # (a handful of small JSON files), so these limits are generous.
    MAX_UPLOAD_BYTES = 10 * 1024 * 1024        # 10 MiB compressed upload
    MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024  # 50 MiB total inflated
    MAX_ENTRIES = 100

    # Read at most MAX_UPLOAD_BYTES + 1 so an oversize upload is detected
    # without buffering the whole thing.
    raw = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Import file too large")

    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid or corrupted zip file")

    infos = zf.infolist()
    if len(infos) > MAX_ENTRIES:
        raise HTTPException(status_code=400, detail="Import archive has too many entries")
    if sum(zi.file_size for zi in infos) > MAX_UNCOMPRESSED_BYTES:
        raise HTTPException(status_code=400, detail="Import archive is too large when decompressed")

    def _read_json(name: str):
        """Read and parse a JSON file from the zip, returning None if missing."""
        try:
            return json.loads(zf.read(name))
        except KeyError:
            return None
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail=f"Invalid JSON in {name}")

    imported: dict[str, Any] = {}
    previous_settings = {row.key: _decode_setting(row.value) for row in db.query(Setting).all()}

    # ── 1. Settings (key-value) ────────────────────────────────────────────
    settings_dict = _read_json("settings.json")
    if settings_dict and isinstance(settings_dict, dict):
        for key, value in settings_dict.items():
            existing = db.get(Setting, key)
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
            row = db.get(StorageBackend, item["id"])
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
            row = db.get(Schedule, item["id"])
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
            row = db.get(RetentionPolicy, item["id"])
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
            row = db.get(NotificationChannel, item["id"])
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
            row = db.get(BackupJob, item["id"])
            if row:
                row.name = item["name"]
                row.label_key = item.get("label_key", "dvbm.job")
                row.label_value = item.get("label_value", "")
                row.storage_id = item["storage_id"]
                row.schedule_id = item.get("schedule_id")
                row.retention_id = item.get("retention_id")
                row.enabled = item.get("enabled", True)
            else:
                db.add(BackupJob(
                    id=item["id"], name=item["name"],
                    label_key=item.get("label_key", "dvbm.job"),
                    label_value=item.get("label_value", ""),
                    storage_id=item["storage_id"],
                    schedule_id=item.get("schedule_id"),
                    retention_id=item.get("retention_id"),
                    enabled=item.get("enabled", True),
                ))
        imported["backup_jobs"] = len(jobs_list)

    db.commit()

    # Sync rclone config to disk if it was part of the import
    if settings_dict and isinstance(settings_dict, dict):
        new_text = rclone_config.config_text_from(settings_dict)
        if new_text:
            config_path = rclone_config.config_path_from(settings_dict)
            plan = rclone_config.plan_write(
                config_path, new_text, rclone_config.config_text_from(previous_settings)
            )
            if plan == "write" or (plan == "confirm" and overwrite_rclone_config):
                rclone_config.write_config(config_path, new_text)
            elif plan == "confirm":
                imported["rclone_config_skipped"] = True
                logger.warning(
                    "Import left the existing rclone config at %s unchanged; "
                    "re-import with overwrite_rclone_config=true to replace it",
                    config_path,
                )

    logger.info("Config imported: %s", imported)
    return {"status": "ok", "imported": imported}
