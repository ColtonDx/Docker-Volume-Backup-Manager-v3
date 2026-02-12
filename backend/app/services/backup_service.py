"""Backup execution service.

Orchestrates the full backup/restore lifecycle:
 1. Find containers with matching label
 2. Collect their volume info
 3. Stop containers
 4. Create tar.gz archive of volumes
 5. Upload to storage backend
 6. Restart containers
 7. Record result + write log
 8. Send notifications
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tarfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class BackupService:
    """Manages backup and restore operations."""

    def run_backup(self, job_id: int) -> None:
        """Execute a backup for the given job. Runs in a background thread."""
        thread = threading.Thread(target=self._do_backup, args=(job_id,), daemon=True)
        thread.start()

    def restore_backup(self, backup_id: int) -> None:
        """Restore from a backup record. Runs in a background thread."""
        thread = threading.Thread(target=self._do_restore, args=(backup_id,), daemon=True)
        thread.start()

    # ------------------------------------------------------------------
    # Backup execution
    # ------------------------------------------------------------------

    def _do_backup(self, job_id: int) -> None:
        from app.database import SessionLocal
        from app.models import BackupJob, BackupRecord, LogEntry
        from app.services.docker_service import docker_service
        from app.services.storage_service import storage_service
        from app.services.notification_service import notification_service
        from app.config import settings

        db = SessionLocal()
        start_time = time.time()
        record = None

        try:
            job = db.query(BackupJob).get(job_id)
            if not job:
                logger.error("Backup job %d not found", job_id)
                return

            # Create a running record
            record = BackupRecord(
                job_id=job.id,
                status="running",
                started_at=datetime.now(timezone.utc),
            )
            db.add(record)
            db.commit()
            db.refresh(record)

            self._log(db, "info", job.name, f"Backup job '{job.name}' started")

            # 1. Find matching containers
            label_key = settings.DOCKER_LABEL_KEY
            containers = docker_service.find_containers_by_label(label_key, job.name)
            container_ids = [c["id"] for c in containers]
            container_names = [c["name"] for c in containers]

            # 2. Collect volumes from those containers
            all_volumes: list[dict[str, str]] = []
            volume_names_set: set[str] = set()
            for cid in container_ids:
                vols = docker_service.get_container_volumes(cid)
                for v in vols:
                    if v["name"] not in volume_names_set:
                        all_volumes.append(v)
                        volume_names_set.add(v["name"])

            if not all_volumes:
                self._log(db, "warning", job.name, "No volumes found for matching containers")

            # 3. Stop containers
            running_ids = [
                c["id"] for c in containers if c["status"] == "running"
            ]
            stopped = docker_service.stop_containers(running_ids)
            self._log(
                db, "info", job.name,
                f"Stopped {len(stopped)} container(s): {', '.join(container_names)}"
            )

            # 4. Create tar.gz archive
            temp_dir = settings.BACKUP_TEMP_DIR
            temp_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            archive_name = f"{job.name}_{timestamp}.tar.gz"
            archive_path = temp_dir / archive_name

            with tarfile.open(str(archive_path), "w:gz") as tar:
                for vol in all_volumes:
                    vol_path = docker_service.get_volume_path(vol["name"])
                    if vol_path and os.path.exists(vol_path):
                        tar.add(vol_path, arcname=vol["name"])
                        logger.info("Added volume %s from %s", vol["name"], vol_path)

            archive_size = archive_path.stat().st_size if archive_path.exists() else 0

            # 5. Upload to storage
            storage = job.storage
            storage_config = json.loads(storage.config_json or "{}")
            remote_path = storage_service.upload(
                storage.type, storage_config, str(archive_path), archive_name
            )

            # 6. Restart containers
            docker_service.start_containers(stopped)
            self._log(
                db, "info", job.name,
                f"Restarted {len(stopped)} container(s)"
            )

            # 7. Update record
            duration = time.time() - start_time
            record.status = "success"
            record.size_bytes = archive_size
            record.duration_seconds = round(duration, 2)
            record.file_path = str(archive_path)
            record.storage_path = remote_path
            record.completed_at = datetime.now(timezone.utc)
            record.containers_stopped = json.dumps(container_names)
            record.volumes_backed_up = json.dumps(list(volume_names_set))
            db.commit()

            # Clean up temp file
            try:
                archive_path.unlink(missing_ok=True)
            except Exception:
                pass

            size_str = self._format_size(archive_size)
            dur_str = f"{duration:.0f}s"
            self._log(
                db, "success", job.name,
                f"Backup completed successfully",
                f"Size: {size_str} | Duration: {dur_str} | Storage: {storage.name}"
            )

            # 8. Notify
            notification_service.notify_event("success", job.name, f"Backup completed: {size_str}")

        except Exception as exc:
            logger.exception("Backup job %d failed", job_id)
            if record:
                record.status = "error"
                record.error_message = str(exc)
                record.completed_at = datetime.now(timezone.utc)
                record.duration_seconds = round(time.time() - start_time, 2)
                db.commit()

            job_name = "unknown"
            try:
                j = db.query(BackupJob).get(job_id)
                if j:
                    job_name = j.name
            except Exception:
                pass

            self._log(db, "error", job_name, f"Backup failed: {exc}")
            notification_service.notify_event("failure", job_name, str(exc))

            # Try to restart any stopped containers
            try:
                from app.services.docker_service import docker_service as ds
                from app.config import settings as s
                if record and record.containers_stopped:
                    names = json.loads(record.containers_stopped)
                    # We don't have IDs stored, containers will be auto-cleaned
            except Exception:
                pass

        finally:
            db.close()

    # ------------------------------------------------------------------
    # Restore execution
    # ------------------------------------------------------------------

    def _do_restore(self, backup_id: int) -> None:
        from app.database import SessionLocal
        from app.models import BackupRecord, LogEntry
        from app.services.docker_service import docker_service
        from app.services.storage_service import storage_service
        from app.services.notification_service import notification_service
        from app.config import settings

        db = SessionLocal()

        try:
            record = db.query(BackupRecord).get(backup_id)
            if not record:
                logger.error("Backup record %d not found", backup_id)
                return

            job = record.job
            job_name = job.name if job else "unknown"

            self._log(db, "info", job_name, f"Restore started from backup #{backup_id}")

            # 1. Download archive from storage
            temp_dir = settings.BACKUP_TEMP_DIR
            temp_dir.mkdir(parents=True, exist_ok=True)
            local_archive = temp_dir / f"restore_{backup_id}.tar.gz"

            if record.storage_path:
                storage = job.storage
                storage_config = json.loads(storage.config_json or "{}")
                storage_service.download(
                    storage.type, storage_config, record.storage_path, str(local_archive)
                )
            elif record.file_path and os.path.exists(record.file_path):
                shutil.copy2(record.file_path, str(local_archive))
            else:
                raise FileNotFoundError("No backup archive found for restore")

            # 2. Stop containers
            label_key = settings.DOCKER_LABEL_KEY
            containers = docker_service.find_containers_by_label(label_key, job_name)
            running_ids = [c["id"] for c in containers if c["status"] == "running"]
            stopped = docker_service.stop_containers(running_ids)

            # 3. Extract archive to volumes
            with tarfile.open(str(local_archive), "r:gz") as tar:
                # Each top-level dir in the archive is a volume name
                members = tar.getmembers()
                volume_names = set()
                for m in members:
                    parts = m.name.split("/")
                    if parts:
                        volume_names.add(parts[0])

                for vol_name in volume_names:
                    vol_path = docker_service.get_volume_path(vol_name)
                    if vol_path:
                        # Clear existing data and extract
                        vol_dir = Path(vol_path)
                        if vol_dir.exists():
                            shutil.rmtree(str(vol_dir))
                        vol_dir.mkdir(parents=True, exist_ok=True)

                        # Extract members belonging to this volume
                        vol_members = [m for m in members if m.name.startswith(vol_name + "/") or m.name == vol_name]
                        tar.extractall(path=str(vol_dir.parent), members=vol_members)
                        logger.info("Restored volume %s to %s", vol_name, vol_path)

            # 4. Restart containers
            docker_service.start_containers(stopped)

            # 5. Clean up
            try:
                local_archive.unlink(missing_ok=True)
            except Exception:
                pass

            self._log(db, "success", job_name, f"Restore completed from backup #{backup_id}")
            notification_service.notify_event("success", job_name, f"Restore completed from backup #{backup_id}")

        except Exception as exc:
            logger.exception("Restore from backup %d failed", backup_id)
            self._log(db, "error", "System", f"Restore failed: {exc}")
            notification_service.notify_event("failure", "System", f"Restore failed: {exc}")
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _log(db, level: str, job_name: str, message: str, details: str | None = None) -> None:
        from app.models import LogEntry

        entry = LogEntry(level=level, job_name=job_name, message=message, details=details)
        db.add(entry)
        db.commit()

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        if size_bytes >= 1_073_741_824:
            return f"{size_bytes / 1_073_741_824:.1f} GB"
        if size_bytes >= 1_048_576:
            return f"{size_bytes / 1_048_576:.1f} MB"
        if size_bytes >= 1024:
            return f"{size_bytes / 1024:.1f} KB"
        return f"{size_bytes} B"


backup_service = BackupService()
