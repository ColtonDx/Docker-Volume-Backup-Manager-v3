from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import BackupRecord
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
