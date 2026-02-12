from datetime import datetime, timedelta, timezone

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
    success_rate = (success_recent / total_recent * 100) if total_recent > 0 else 100.0

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

    # Upcoming schedules
    schedules = db.query(Schedule).filter(Schedule.enabled == True).all()
    upcoming = [
        {
            "id": s.id,
            "name": s.name,
            "cron": s.cron,
            "description": s.description,
        }
        for s in schedules[:5]
    ]

    return DashboardStats(
        total_jobs=total_jobs,
        active_jobs=active_jobs,
        storage_backends_count=storage_count,
        success_rate_30d=round(success_rate, 1),
        active_alerts=active_alerts,
        recent_jobs=recent_jobs,
        upcoming_schedules=upcoming,
    )
