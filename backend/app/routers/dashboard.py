from datetime import datetime, timedelta, timezone

from apscheduler.triggers.cron import CronTrigger
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import BackupJob, BackupRecord, LogEntry, StorageBackend, Schedule
from app.schemas import DashboardStats

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("", response_model=DashboardStats)
def get_dashboard(db: Session = Depends(get_db)):
    total_jobs = db.query(BackupJob).count()
    active_jobs = db.query(BackupJob).filter(BackupJob.enabled == True).count()
    storage_count = db.query(StorageBackend).count()

    # Success rate over last 30 days
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    recent_records = (
        db.query(BackupRecord)
        .filter(BackupRecord.started_at >= thirty_days_ago)
        .all()
    )
    total_recent = len(recent_records)
    success_recent = sum(1 for r in recent_records if r.status == "success")
    success_rate = (success_recent / total_recent * 100) if total_recent > 0 else -1.0

    # Active alerts: count of error records in last 24h
    one_day_ago = datetime.now(timezone.utc) - timedelta(days=1)
    active_alerts = (
        db.query(BackupRecord)
        .filter(
            BackupRecord.started_at >= one_day_ago,
            BackupRecord.status.in_(["error", "warning"]),
        )
        .count()
    )

    # Recent backup records
    recent_jobs = (
        db.query(BackupRecord)
        .order_by(BackupRecord.started_at.desc())
        .limit(5)
        .all()
    )

    # Upcoming schedules — include next run time and linked job names
    schedules = db.query(Schedule).filter(Schedule.enabled == True).all()
    now = datetime.now(timezone.utc)
    upcoming = []
    for s in schedules:
        # Compute next_run from cron expression
        next_run = None
        try:
            parts = s.cron.strip().split()
            if len(parts) == 5:
                trigger = CronTrigger(
                    minute=parts[0], hour=parts[1], day=parts[2],
                    month=parts[3], day_of_week=parts[4],
                )
                next_fire = trigger.get_next_fire_time(None, now)
                if next_fire:
                    next_run = next_fire.isoformat()
        except Exception:
            pass

        # Find jobs linked to this schedule
        linked_jobs = (
            db.query(BackupJob)
            .filter(BackupJob.schedule_id == s.id, BackupJob.enabled == True)
            .all()
        )
        job_names = [j.name for j in linked_jobs]

        upcoming.append({
            "id": s.id,
            "name": s.name,
            "cron": s.cron,
            "description": s.description,
            "next_run": next_run,
            "job_names": job_names,
        })

    # Sort by next_run (soonest first), entries with no next_run go last
    upcoming.sort(key=lambda x: x["next_run"] or "9999")
    upcoming = upcoming[:5]

    return DashboardStats(
        total_jobs=total_jobs,
        active_jobs=active_jobs,
        storage_backends_count=storage_count,
        success_rate_30d=round(success_rate, 1),
        active_alerts=active_alerts,
        recent_jobs=recent_jobs,
        upcoming_schedules=upcoming,
    )
