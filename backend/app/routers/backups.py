from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import BackupJob, BackupRecord
from app.schemas import BackupRecordOut

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("", response_model=List[BackupRecordOut])
def list_backups(
    job_id: int | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    db: Session = Depends(get_db),
):
    q = db.query(BackupRecord).order_by(BackupRecord.started_at.desc())
    if job_id is not None:
        q = q.filter(BackupRecord.job_id == job_id)
    if status is not None:
        q = q.filter(BackupRecord.status == status)
    return q.offset(offset).limit(limit).all()


@router.get("/{backup_id}", response_model=BackupRecordOut)
def get_backup(backup_id: int, db: Session = Depends(get_db)):
    record = db.query(BackupRecord).get(backup_id)
    if not record:
        raise HTTPException(status_code=404, detail="Backup record not found")
    return record


@router.post("/{backup_id}/restore")
def restore_backup(backup_id: int, db: Session = Depends(get_db)):
    """Restore volumes from a backup record."""
    record = db.query(BackupRecord).get(backup_id)
    if not record:
        raise HTTPException(status_code=404, detail="Backup record not found")
    if record.status != "success":
        raise HTTPException(
            status_code=400,
            detail="Can only restore from successful backups",
        )

    from app.services.backup_service import backup_service
    backup_service.restore_backup(backup_id)
    return {"message": f"Restore initiated from backup #{backup_id}"}


@router.delete("/{backup_id}", status_code=204)
def delete_backup(backup_id: int, db: Session = Depends(get_db)):
    record = db.query(BackupRecord).get(backup_id)
    if not record:
        raise HTTPException(status_code=404, detail="Backup record not found")
    db.delete(record)
    db.commit()


@router.post("/import")
def import_backups(job_id: int = Query(...), db: Session = Depends(get_db)):
    """Scan a job's storage backend for existing backup archives and import them as records."""
    import json
    import re
    from datetime import datetime, timezone

    job = db.query(BackupJob).get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Backup job not found")

    storage = job.storage
    if not storage:
        raise HTTPException(status_code=400, detail="Job has no storage backend configured")

    config = json.loads(storage.config_json or "{}")
    from app.services.storage_service import storage_service

    try:
        files = storage_service.list_files(storage.type, config, prefix=f"{job.name}_")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to list files: {exc}")

    # Get existing storage_paths to avoid duplicates
    existing_paths = set(
        r[0] for r in db.query(BackupRecord.storage_path)
        .filter(BackupRecord.job_id == job.id, BackupRecord.storage_path.isnot(None))
        .all()
    )

    # Pattern: {job_name}_{YYYYMMDD_HHMMSS}.tar.gz
    pattern = re.compile(
        rf"^{re.escape(job.name)}_(\d{{4}})(\d{{2}})(\d{{2}})_(\d{{2}})(\d{{2}})(\d{{2}})\.tar\.gz$"
    )

    imported = 0
    skipped = 0
    for f in files:
        if f["path"] in existing_paths:
            skipped += 1
            continue

        # Try to parse timestamp from filename
        m = pattern.match(f["name"])
        if m:
            y, mo, d, h, mi, s = (int(x) for x in m.groups())
            try:
                ts = datetime(y, mo, d, h, mi, s, tzinfo=timezone.utc)
            except ValueError:
                ts = datetime.now(timezone.utc)
        else:
            # Non-standard name but still matches prefix + .tar.gz
            ts = datetime.now(timezone.utc)

        record = BackupRecord(
            job_id=job.id,
            status="success",
            size_bytes=f.get("size"),
            duration_seconds=None,
            file_path=None,
            storage_path=f["path"],
            started_at=ts,
            completed_at=ts,
            error_message=None,
            containers_stopped="[]",
            volumes_backed_up="[]",
        )
        db.add(record)
        imported += 1

    if imported > 0:
        db.commit()

    # Log the import operation
    from app.models import LogEntry
    level = "success" if imported > 0 else "info"
    log_msg = f"Import scan: {imported} backup(s) imported, {skipped} skipped, {len(files)} found on storage"
    db.add(LogEntry(level=level, job_name=job.name, message=log_msg))
    db.commit()

    return {
        "imported": imported,
        "skipped": skipped,
        "total_found": len(files),
        "message": f"Imported {imported} backup(s), skipped {skipped} already known",
    }
