"""Scheduler service using APScheduler.

Reads cron schedules from the database and registers APScheduler jobs
that trigger backups at the configured times.
"""

from __future__ import annotations

import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

# How late a missed run may still fire (seconds). Covers a short outage or a
# restart around the scheduled time rather than skipping the run entirely.
_MISFIRE_GRACE_SECONDS = int(os.getenv("MISFIRE_GRACE_SECONDS", "3600"))


class SchedulerService:
    """Manages the APScheduler instance that fires backup jobs on cron schedules."""

    def __init__(self) -> None:
        self._scheduler: BackgroundScheduler | None = None

    @staticmethod
    def _normalise_tz(tz: str) -> str:
        """APScheduler 3.11+ uses zoneinfo which requires exact IANA keys (case-sensitive)."""
        stripped = tz.strip()
        if stripped.upper() == "UTC":
            return "UTC"
        return stripped

    @staticmethod
    def _validate_tz(tz: str) -> str:
        """Return *tz* if zoneinfo can load it, else raise ValueError.

        Checked before the running scheduler is touched: shutting it down and
        then failing to build the replacement left the app with no scheduler
        at all until the process was restarted.
        """
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(tz)
        except (ZoneInfoNotFoundError, ValueError, KeyError) as exc:
            raise ValueError(f"Unknown timezone '{tz}': {exc}") from exc
        return tz

    def start(self) -> None:
        """Start the scheduler and sync jobs from the database."""
        from app.config import settings
        tz = self._normalise_tz(settings.TIMEZONE)
        settings.TIMEZONE = tz  # ensure downstream code (e.g. _parse_cron) sees the normalized value
        self._scheduler = BackgroundScheduler(timezone=tz)
        self._scheduler.start()
        self.sync_jobs()
        logger.info("Scheduler started with timezone '%s'", tz)

    def shutdown(self) -> None:
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Scheduler shut down")

    def reconfigure_timezone(self, tz: str) -> None:
        """Restart the scheduler with a new timezone and re-sync all jobs."""
        from app.config import settings
        tz = self._normalise_tz(tz)
        # Validate first: a bad value must not take the running scheduler down.
        self._validate_tz(tz)
        was_running = self._scheduler and self._scheduler.running
        if was_running:
            self._scheduler.shutdown(wait=False)
        settings.TIMEZONE = tz
        self._scheduler = BackgroundScheduler(timezone=tz)
        if was_running:
            self._scheduler.start()
            self.sync_jobs()
        logger.info("Scheduler reconfigured with timezone '%s'", tz)

    def sync_jobs(self) -> None:
        """Synchronise APScheduler jobs with the database.

        Call this after any change to schedules or backup jobs.
        """
        if not self._scheduler or not self._scheduler.running:
            return

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
                    self._scheduler.add_job(  # type: ignore[union-attr]
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
                        # Without this APScheduler's 1-second default silently
                        # drops any run missed while the host was down.
                        misfire_grace_time=_MISFIRE_GRACE_SECONDS,
                    )
                    logger.info(
                        "Scheduled job '%s' (id=%d) with cron '%s'",
                        bj.name, bj.id, schedule.cron,
                    )
                except Exception as exc:
                    logger.error(
                        "Failed to schedule job '%s': %s", bj.name, exc
                    )

            # Register the automated config backup job if configured
            try:
                self._sync_config_backup(db)
            except Exception as exc:
                logger.error("Failed to sync config backup job: %s", exc)

            # Daily log pruning — enforces the log_retention_* settings, which
            # previously existed in the UI but were never acted on.
            try:
                self._scheduler.add_job(  # type: ignore[union-attr]
                    self._prune_logs,
                    trigger=CronTrigger(hour=3, minute=30),
                    id="dvbm-log-retention",
                    replace_existing=True,
                    name="log-retention",
                    max_instances=1,
                    coalesce=True,
                    misfire_grace_time=_MISFIRE_GRACE_SECONDS,
                )
            except Exception as exc:
                logger.error("Failed to register log retention job: %s", exc)
        finally:
            db.close()

    @staticmethod
    def _prune_logs() -> None:
        """Delete log entries older than the configured retention windows."""
        import json
        from datetime import datetime, timedelta, timezone

        from app.database import SessionLocal
        from app.models import LogEntry, Setting

        db = SessionLocal()
        try:
            def _get(key, default):
                row = db.get(Setting, key)
                if row is None or row.value is None:
                    return default
                try:
                    return json.loads(row.value)
                except (json.JSONDecodeError, TypeError):
                    return default

            backup_days = int(_get("log_retention_backup_days", 30) or 0)
            system_days = int(_get("log_retention_system_days", 14) or 0)
            now = datetime.now(timezone.utc)
            removed = 0

            if system_days > 0:
                cutoff = now - timedelta(days=system_days)
                removed += (
                    db.query(LogEntry)
                    .filter(LogEntry.job_name == "System", LogEntry.created_at < cutoff)
                    .delete(synchronize_session=False)
                )

            if backup_days > 0:
                cutoff = now - timedelta(days=backup_days)
                removed += (
                    db.query(LogEntry)
                    .filter(LogEntry.job_name != "System", LogEntry.created_at < cutoff)
                    .delete(synchronize_session=False)
                )

            if removed:
                db.add(LogEntry(
                    level="info",
                    job_name="System",
                    message=f"Log retention: removed {removed} old log entr(ies)",
                    details=(
                        f"Backup logs older than {backup_days}d, "
                        f"system logs older than {system_days}d"
                    ),
                ))
            db.commit()
            logger.info("Log retention pruned %d entries", removed)
        except Exception as exc:
            logger.error("Log retention pruning failed: %s", exc)
            db.rollback()
        finally:
            db.close()

    def _sync_config_backup(self, db) -> None:
        """Register or remove the automated config backup APScheduler job."""
        import json

        from app.models import Schedule, Setting

        CONFIG_JOB_ID = "dvbm-config-backup"

        # Read relevant settings
        def _get(key, default=None):
            row = db.get(Setting, key)
            if row is None:
                return default
            try:
                return json.loads(row.value)
            except (json.JSONDecodeError, TypeError):
                return row.value

        enabled = _get("config_backup_enabled", False)
        schedule_id = _get("config_backup_schedule_id")

        if not enabled or not schedule_id:
            # Remove the job if it was previously scheduled
            if self._scheduler.get_job(CONFIG_JOB_ID):  # type: ignore[union-attr]
                self._scheduler.remove_job(CONFIG_JOB_ID)  # type: ignore[union-attr]
                logger.info("Config backup cron job removed")
            return

        schedule = db.get(Schedule, int(schedule_id))
        if not schedule or not schedule.enabled or not schedule.cron:
            if self._scheduler.get_job(CONFIG_JOB_ID):  # type: ignore[union-attr]
                self._scheduler.remove_job(CONFIG_JOB_ID)  # type: ignore[union-attr]
            return

        try:
            trigger = self._parse_cron(schedule.cron)
            self._scheduler.add_job(  # type: ignore[union-attr]
                self._run_config_backup,
                trigger=trigger,
                id=CONFIG_JOB_ID,
                replace_existing=True,
                name="dvbm-config-backup",
                max_instances=1,
                coalesce=True,
                misfire_grace_time=_MISFIRE_GRACE_SECONDS,
            )
            logger.info("Config backup scheduled with cron '%s'", schedule.cron)
        except Exception as exc:
            logger.error("Failed to schedule config backup: %s", exc)

    @staticmethod
    def _run_backup(job_id: int) -> None:
        """Callback invoked by APScheduler to trigger a backup."""
        from app.services.backup_service import backup_service

        logger.info("Cron trigger: running backup job %d", job_id)
        backup_service.run_backup(job_id)

    @staticmethod
    def _run_config_backup() -> None:
        """Callback invoked by APScheduler to trigger a config backup."""
        from app.services.config_backup_service import config_backup_service

        logger.info("Cron trigger: running config backup")
        config_backup_service.run()

    @staticmethod
    def _parse_cron(cron_expr: str) -> CronTrigger:
        """Parse a 5-field cron expression into an APScheduler CronTrigger.

        Format: minute hour day_of_month month day_of_week
        """
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            raise ValueError(f"Invalid cron expression (need 5 fields): {cron_expr}")

        from app.config import settings
        minute, hour, day, month, day_of_week = parts
        return CronTrigger(
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
            timezone=SchedulerService._normalise_tz(settings.TIMEZONE),
        )


scheduler_service = SchedulerService()
