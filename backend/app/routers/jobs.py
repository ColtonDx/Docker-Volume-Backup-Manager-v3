import json
from datetime import datetime, timedelta, timezone
from typing import List

from apscheduler.triggers.cron import CronTrigger
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import BackupJob, BackupRecord, LogEntry
from app.schemas import BackupJobCreate, BackupJobOut, BackupJobUpdate, BackupRecordOut, JobDetailStats, LogEntryOut
from app.services.backup_service import backup_service
from app.services.docker_service import docker_service
from app.services.scheduler_service import scheduler_service

router = APIRouter(dependencies=[Depends(get_current_user)])


def _enrich_job(job: BackupJob, db: Session) -> dict:
    """Add dynamic fields like matched containers, status, last/next run."""
    label_key = job.label_key or "backup-buddy.job"
    label_value = job.label_value or job.name
    containers = docker_service.find_containers_by_label(label_key, label_value)
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
        "label_key": label_key,
        "label_value": label_value,
        "label": f"{label_key}={label_value}",
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
        label_key=body.label_key,
        label_value=body.label_value or body.name,
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


@router.get("/{job_id}/stats", response_model=JobDetailStats)
def get_job_stats(job_id: int, db: Session = Depends(get_db)):
    """Per-job dashboard stats: success rate, backup history, schedule, logs."""
    job = db.query(BackupJob).get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    enriched = _enrich_job(job, db)

    # All backup records for this job
    all_records = (
        db.query(BackupRecord)
        .filter(BackupRecord.job_id == job.id)
        .order_by(BackupRecord.started_at.desc())
        .all()
    )

    # 30-day success rate  (SQLite returns naive datetimes, so compare with naive UTC)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    recent_records = [r for r in all_records if r.started_at and r.started_at >= thirty_days_ago]
    total_recent = len(recent_records)
    success_recent = sum(1 for r in recent_records if r.status == "success")
    success_rate = round((success_recent / total_recent * 100) if total_recent > 0 else -1.0, 1)

    # Aggregated stats
    total_backups = len(all_records)
    total_size = sum(r.size_bytes or 0 for r in all_records)
    avg_duration = None
    durations = [r.duration_seconds for r in all_records if r.duration_seconds is not None]
    if durations:
        avg_duration = round(sum(durations) / len(durations), 1)

    # Error count in last 24h
    one_day_ago = datetime.utcnow() - timedelta(days=1)
    errors_24h = sum(
        1 for r in all_records
        if r.started_at and r.started_at >= one_day_ago and r.status in ("error", "warning")
    )

    # Recent backup records (last 20)
    recent_backups = all_records[:20]

    # Recent logs for this job
    logs = (
        db.query(LogEntry)
        .filter(LogEntry.job_name == job.name)
        .order_by(LogEntry.created_at.desc())
        .limit(50)
        .all()
    )

    # Schedule info
    schedule_info = None
    if job.schedule:
        next_run = None
        try:
            parts = job.schedule.cron.strip().split()
            if len(parts) == 5:
                trigger = CronTrigger(
                    minute=parts[0], hour=parts[1], day=parts[2],
                    month=parts[3], day_of_week=parts[4],
                )
                next_fire = trigger.get_next_fire_time(None, datetime.now(timezone.utc))
                if next_fire:
                    next_run = next_fire.isoformat()
        except Exception:
            pass
        schedule_info = {
            "name": job.schedule.name,
            "cron": job.schedule.cron,
            "next_run": next_run,
        }

    return JobDetailStats(
        job=enriched,
        success_rate_30d=success_rate,
        total_backups=total_backups,
        total_size_bytes=total_size,
        avg_duration_seconds=avg_duration,
        errors_24h=errors_24h,
        recent_backups=recent_backups,
        logs=logs,
        schedule_info=schedule_info,
    )
