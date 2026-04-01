"""Scheduler service using APScheduler.

Reads cron schedules from the database and registers APScheduler jobs
that trigger backups at the configured times.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


class SchedulerService:
    """Manages the APScheduler instance that fires backup jobs on cron schedules."""

    def __init__(self) -> None:
        self._scheduler = BackgroundScheduler(timezone="UTC")

    def start(self) -> None:
        """Start the scheduler and sync jobs from the database."""
        self._scheduler.start()
        self.sync_jobs()
        logger.info("Scheduler started")

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Scheduler shut down")

    def sync_jobs(self) -> None:
        """Synchronise APScheduler jobs with the database.

        Call this after any change to schedules or backup jobs.
        """
        from app.database import SessionLocal
        from app.models import BackupJob

        # Remove all existing jobs first
        for job in self._scheduler.get_jobs():
            job.remove()

        db = SessionLocal()
        try:
            jobs = (
                db.query(BackupJob)
                .filter(BackupJob.enabled == True, BackupJob.schedule_id.isnot(None))
                .all()
            )
            for bj in jobs:
                schedule = bj.schedule
                if not schedule or not schedule.enabled or not schedule.cron:
                    continue
                try:
                    trigger = self._parse_cron(schedule.cron)
                    self._scheduler.add_job(
                        self._run_backup,
                        trigger=trigger,
                        args=[bj.id],
                        id=f"backup-job-{bj.id}",
                        replace_existing=True,
                        name=f"backup-{bj.name}",
                        # Prevent a second instance starting if the first is still running.
                        max_instances=1,
                        # If a trigger was missed while the job was running, run it
                        # once when it's free rather than queuing up every missed fire.
                        coalesce=True,
                    )
                    logger.info(
                        "Scheduled job '%s' (id=%d) with cron '%s'",
                        bj.name, bj.id, schedule.cron,
                    )
                except Exception as exc:
                    logger.error(
                        "Failed to schedule job '%s': %s", bj.name, exc
                    )
        finally:
            db.close()

    @staticmethod
    def _run_backup(job_id: int) -> None:
        """Callback invoked by APScheduler to trigger a backup."""
        from app.services.backup_service import backup_service

        logger.info("Cron trigger: running backup job %d", job_id)
        backup_service.run_backup(job_id)

    @staticmethod
    def _parse_cron(cron_expr: str) -> CronTrigger:
        """Parse a 5-field cron expression into an APScheduler CronTrigger.

        Format: minute hour day_of_month month day_of_week
        """
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            raise ValueError(f"Invalid cron expression (need 5 fields): {cron_expr}")

        minute, hour, day, month, day_of_week = parts
        return CronTrigger(
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
        )


scheduler_service = SchedulerService()
