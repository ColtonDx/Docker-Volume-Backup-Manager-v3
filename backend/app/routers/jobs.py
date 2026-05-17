import json
from datetime import datetime, timedelta, timezone
from typing import List

from apscheduler.triggers.cron import CronTrigger
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import BackupJob, BackupRecord, LogEntry
from app.schemas import BackupJobCreate, BackupJobOut, BackupJobUpdate, BackupRecordOut, JobDetailStats, LogEntryOut
from app.services.backup_service import backup_service
from app.services.docker_service import docker_service
from app.services.scheduler_service import scheduler_service

router = APIRouter(dependencies=[Depends(get_current_user)])


def _enrich_job(
    job: BackupJob,
    db: Session,
    all_containers: list[dict] | None = None,
    last_records: dict[int, BackupRecord] | None = None,
) -> dict:
    """Add dynamic fields like matched containers, status, last/next run.

    When called from list_jobs, all_containers and last_records are pre-fetched
    in bulk (one Docker call + one DB query for the whole list). When called for
    a single job these are None and the individual lookups are performed instead.
    """
    label_key = job.label_key or "dvbm.job"
    label_value = job.label_value or job.name

    if all_containers is not None:
        # Match from the pre-fetched list — no Docker call needed
        container_names = [
            c["name"] for c in all_containers
            if c.get("labels", {}).get(label_key) == label_value
        ]
    else:
        containers = docker_service.find_containers_by_label(label_key, label_value)
        container_names = [c["name"] for c in containers]

    # Determine status from most recent backup record
    if last_records is not None:
        last_record: BackupRecord | None = last_records.get(job.id)
    else:
        last_record = (
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
        "timeout_seconds": job.timeout_seconds,
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
    if not jobs:
        return []

    # One Docker call for all containers (instead of one per job)
    all_containers = docker_service.list_containers(all=True)

    # One DB query for the most recent backup record per job (instead of one per job)
    subq = (
        db.query(
            BackupRecord.job_id,
            func.max(BackupRecord.started_at).label("max_started"),
        )
        .group_by(BackupRecord.job_id)
        .subquery()
    )
    last_records: dict[int, BackupRecord] = {
        r.job_id: r
        for r in db.query(BackupRecord).join(
            subq,
            (BackupRecord.job_id == subq.c.job_id)
            & (BackupRecord.started_at == subq.c.max_started),
        ).all()
    }

    return [_enrich_job(j, db, all_containers, last_records) for j in jobs]


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
        timeout_seconds=body.timeout_seconds,
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

    # SQLite returns naive datetimes, compare with naive UTC
    thirty_days_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)
    one_day_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)

    # All aggregated stats in a single SQL query — no Python loops over full record set
    agg = (
        db.query(
            func.count().label("total_backups"),
            func.coalesce(func.sum(BackupRecord.size_bytes), 0).label("total_size"),
            func.avg(BackupRecord.duration_seconds).label("avg_duration"),
            func.sum(case((BackupRecord.started_at >= thirty_days_ago, 1), else_=0)).label("total_recent"),
            func.sum(case((
                (BackupRecord.started_at >= thirty_days_ago) & (BackupRecord.status == "success"), 1
            ), else_=0)).label("success_recent"),
            func.sum(case((
                (BackupRecord.started_at >= one_day_ago) & BackupRecord.status.in_(["error", "warning"]), 1
            ), else_=0)).label("errors_24h"),
        )
        .filter(BackupRecord.job_id == job.id)
        .one()
    )

    total_backups = agg.total_backups or 0
    total_size = agg.total_size or 0
    avg_duration = round(float(agg.avg_duration), 1) if agg.avg_duration is not None else None
    total_recent = agg.total_recent or 0
    success_recent = agg.success_recent or 0
    errors_24h = agg.errors_24h or 0
    success_rate = round((success_recent / total_recent * 100) if total_recent > 0 else -1.0, 1)

    # Recent backup records (last 20 only — no full table scan)
    recent_backups = (
        db.query(BackupRecord)
        .filter(BackupRecord.job_id == job.id)
        .order_by(BackupRecord.started_at.desc())
        .limit(20)
        .all()
    )

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
