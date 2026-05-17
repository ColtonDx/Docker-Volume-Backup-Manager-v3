from datetime import datetime, timedelta, timezone

from apscheduler.triggers.cron import CronTrigger
from fastapi import APIRouter, Depends
from sqlalchemy import func, case
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

    # Success rate over last 30 days — computed in SQL, no Python loop
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    rate_row = (
        db.query(
            func.count().label("total"),
            func.sum(case((BackupRecord.status == "success", 1), else_=0)).label("successes"),
        )
        .filter(BackupRecord.started_at >= thirty_days_ago)
        .one()
    )
    total_recent = rate_row.total or 0
    success_recent = rate_row.successes or 0
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

    # Single bulk query for all jobs linked to enabled schedules (replaces N+1 loop)
    schedule_ids = [s.id for s in schedules]
    linked_jobs_all = (
        db.query(BackupJob.schedule_id, BackupJob.name)
        .filter(BackupJob.schedule_id.in_(schedule_ids), BackupJob.enabled == True)
        .all()
    ) if schedule_ids else []
    jobs_by_schedule: dict[int, list[str]] = {}
    for job_schedule_id, job_name in linked_jobs_all:
        jobs_by_schedule.setdefault(job_schedule_id, []).append(job_name)

    upcoming = []
    for s in schedules:
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

        upcoming.append({
            "id": s.id,
            "name": s.name,
            "cron": s.cron,
            "description": s.description,
            "next_run": next_run,
            "job_names": jobs_by_schedule.get(s.id, []),
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
