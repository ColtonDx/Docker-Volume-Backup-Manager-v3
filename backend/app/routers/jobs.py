import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import BackupJob, BackupRecord
from app.schemas import BackupJobCreate, BackupJobOut, BackupJobUpdate
from app.services.backup_service import backup_service
from app.services.docker_service import docker_service
from app.services.scheduler_service import scheduler_service

router = APIRouter(dependencies=[Depends(get_current_user)])


def _enrich_job(job: BackupJob, db: Session) -> dict:
    """Add dynamic fields like matched containers, status, last/next run."""
    label_key = "backup-buddy.job"
    containers = docker_service.find_containers_by_label(label_key, job.name)
    container_names = [c["name"] for c in containers]

    # Determine status from most recent backup record
    last_record: BackupRecord | None = (
        db.query(BackupRecord)
        .filter(BackupRecord.job_id == job.id)
        .order_by(BackupRecord.started_at.desc())
        .first()
    )
    if last_record:
        if last_record.status == "running":
            status = "running"
        elif last_record.status == "error":
            status = "error"
        else:
            status = "active" if job.enabled else "idle"
        last_run = last_record.started_at.isoformat() if last_record.started_at else None
    else:
        status = "active" if job.enabled else "idle"
        last_run = None

    # Next run from schedule
    next_run: str | None = None
    if job.schedule and job.schedule.cron and job.enabled:
        next_run = f"Scheduled ({job.schedule.cron})"

    return {
        "id": job.id,
        "name": job.name,
        "label": f"backup-buddy.job={job.name}",
        "enabled": job.enabled,
        "storage": job.storage,
        "schedule": job.schedule,
        "retention": job.retention,
        "containers": container_names,
        "status": status,
        "last_run": last_run,
        "next_run": next_run,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


@router.get("", response_model=List[BackupJobOut])
def list_jobs(db: Session = Depends(get_db)):
    jobs = db.query(BackupJob).all()
    return [_enrich_job(j, db) for j in jobs]


@router.get("/{job_id}", response_model=BackupJobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(BackupJob).get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _enrich_job(job, db)


@router.post("", response_model=BackupJobOut, status_code=201)
def create_job(body: BackupJobCreate, db: Session = Depends(get_db)):
    job = BackupJob(
        name=body.name,
        storage_id=body.storage_id,
        schedule_id=body.schedule_id,
        retention_id=body.retention_id,
        enabled=body.enabled,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    scheduler_service.sync_jobs()
    return _enrich_job(job, db)


@router.put("/{job_id}", response_model=BackupJobOut)
def update_job(job_id: int, body: BackupJobUpdate, db: Session = Depends(get_db)):
    job = db.query(BackupJob).get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(job, field, value)
    db.commit()
    db.refresh(job)
    scheduler_service.sync_jobs()
    return _enrich_job(job, db)


@router.delete("/{job_id}", status_code=204)
def delete_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(BackupJob).get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    db.delete(job)
    db.commit()
    scheduler_service.sync_jobs()


@router.post("/{job_id}/run")
def run_job_now(job_id: int, db: Session = Depends(get_db)):
    """Manually trigger a backup job."""
    job = db.query(BackupJob).get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    backup_service.run_backup(job_id)
    return {"message": f"Backup job '{job.name}' triggered"}


@router.post("/{job_id}/pause")
def pause_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(BackupJob).get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job.enabled = False
    db.commit()
    scheduler_service.sync_jobs()
    return {"message": f"Job '{job.name}' paused"}


@router.post("/{job_id}/resume")
def resume_job(job_id: int, db: Session = Depends(get_db)):
    job = db.query(BackupJob).get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job.enabled = True
    db.commit()
    scheduler_service.sync_jobs()
    return {"message": f"Job '{job.name}' resumed"}
