"""Rotation / retention service.

Applies retention policies by deleting old backup records and their
corresponding files from storage backends.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


class RotationService:
    """Enforces backup retention policies."""

    def apply_policy(self, policy_id: int) -> int:
        """Apply a single retention policy. Returns number of removed backups."""
        from app.database import SessionLocal
        from app.models import BackupJob, BackupRecord, RetentionPolicy, LogEntry
        from app.services.storage_service import storage_service

        db = SessionLocal()
        removed = 0

        try:
            policy = db.query(RetentionPolicy).get(policy_id)
            if not policy:
                return 0

            # Find all jobs using this policy
            jobs = db.query(BackupJob).filter(BackupJob.retention_id == policy_id).all()

            for job in jobs:
                records = (
                    db.query(BackupRecord)
                    .filter(
                        BackupRecord.job_id == job.id,
                        BackupRecord.status == "success",
                    )
                    .order_by(BackupRecord.started_at.desc())
                    .all()
                )

                if not records:
                    continue

                cutoff = datetime.now(timezone.utc) - timedelta(days=policy.retention_days)

                # Always keep at least min_backups
                to_keep = max(policy.min_backups, 0)
                kept = 0
                to_delete: list[BackupRecord] = []

                for rec in records:
                    if kept < to_keep:
                        kept += 1
                        continue
                    # If max_backups is set and we're over, delete
                    if policy.max_backups and kept >= policy.max_backups:
                        to_delete.append(rec)
                        continue
                    # Delete if older than retention period
                    if rec.started_at and rec.started_at.replace(tzinfo=timezone.utc) < cutoff:
                        to_delete.append(rec)
                    else:
                        kept += 1

                for rec in to_delete:
                    # Try to delete from storage
                    if rec.storage_path and job.storage:
                        try:
                            config = json.loads(job.storage.config_json or "{}")
                            storage_service.delete_remote(job.storage.type, config, rec.storage_path)
                        except Exception as exc:
                            logger.warning("Failed to delete remote file %s: %s", rec.storage_path, exc)

                    db.delete(rec)
                    removed += 1

            if removed > 0:
                db.add(LogEntry(
                    level="info",
                    job_name="System",
                    message=f"Retention policy '{policy.name}' applied",
                    details=f"Removed {removed} backup(s)",
                ))
            db.commit()

        except Exception as exc:
            logger.exception("Failed to apply retention policy %d: %s", policy_id, exc)
            db.rollback()
        finally:
            db.close()

        return removed

    def apply_all_policies(self) -> int:
        """Apply all retention policies. Returns total removed."""
        from app.database import SessionLocal
        from app.models import RetentionPolicy

        db = SessionLocal()
        total = 0
        try:
            policies = db.query(RetentionPolicy).all()
            policy_ids = [p.id for p in policies]
        finally:
            db.close()

        for pid in policy_ids:
            total += self.apply_policy(pid)

        return total


rotation_service = RotationService()
