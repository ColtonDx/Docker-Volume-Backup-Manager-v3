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
import multiprocessing
import os
import shutil
import tarfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def _compress_level(db=None) -> int:
    """gzip level for backup archives.

    Level 9 (tarfile's default) is markedly slower for a few percent of size on
    already-compressed data. The default_compression setting was read but never
    actually applied to the archive.
    """
    from app.config import settings
    from app.models import Setting

    choice = settings.DEFAULT_COMPRESSION or "gzip"
    if db is not None:
        try:
            row = db.get(Setting, "default_compression")
            if row is not None and row.value is not None:
                choice = json.loads(row.value)
        except Exception as exc:
            logger.debug("Could not read default_compression setting: %s", exc)

    mapping = {"none": 1, "fast": 1, "gzip": 6, "balanced": 6, "max": 9, "best": 9}
    return mapping.get(str(choice).strip().lower(), 6)


def _verify_backups_enabled(db) -> bool:
    """Read the verify_backups setting (defaults to on).

    Setting values are JSON-encoded by the settings router.
    """
    from app.models import Setting

    try:
        row = db.get(Setting, "verify_backups")
    except Exception as exc:
        logger.warning("Could not read verify_backups setting: %s", exc)
        return True
    if row is None or row.value is None:
        return True
    try:
        return bool(json.loads(row.value))
    except (json.JSONDecodeError, TypeError):
        return str(row.value).strip().lower() not in ("false", "0", "no", "off")


# ----------------------------------------------------------------------------
# Subprocess entry points
# ----------------------------------------------------------------------------
# Backup/restore work runs in a separate process (spawn) so a job that exceeds
# its timeout can be forcibly killed — a thread cannot. These must be module
# level so the spawn start method can import them by name. Each rebuilds its own
# DB/Docker state from the fresh interpreter.

def _run_backup_entry(job_id: int) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    from app.services.backup_service import backup_service
    backup_service._run_backup(job_id)


def _run_restore_entry(backup_id: int) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    from app.services.backup_service import backup_service
    backup_service._run_restore(backup_id)


class BackupService:
    """Manages backup and restore operations."""

    def __init__(self) -> None:
        from app.config import settings
        # Semaphore limits how many backup/restore threads run simultaneously.
        # Default is 1 (sequential) to prevent concurrent jobs from stopping
        # the same containers or corrupting shared volumes.
        self._semaphore = threading.Semaphore(settings.MAX_CONCURRENT_BACKUPS)
        # Tracks job IDs waiting for the semaphore (not yet running).
        self._queued: set[int] = set()
        self._queue_lock = threading.Lock()

    @property
    def queued_job_ids(self) -> frozenset[int]:
        with self._queue_lock:
            return frozenset(self._queued)

    def run_backup(self, job_id: int) -> None:
        """Execute a backup for the given job. Runs in a background thread."""
        with self._queue_lock:
            self._queued.add(job_id)
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
        with self._semaphore:
            with self._queue_lock:
                self._queued.discard(job_id)
            self._run_with_timeout(job_id, kind="backup")

    def _do_restore(self, backup_id: int) -> None:
        with self._semaphore:
            self._run_with_timeout(backup_id, kind="restore")

    def _run_with_timeout(self, entity_id: int, kind: str) -> None:
        """Run a backup or restore in a child thread, enforcing a per-job timeout.

        Resolves timeout from (in priority order):
          1. The job's own timeout_seconds field (if set)
          2. The JOB_TIMEOUT_SECONDS global default
          3. No timeout if both are 0
        """
        from app.config import settings
        from app.database import SessionLocal
        from app.models import BackupJob

        # Resolve the timeout for this specific job
        timeout: int | None = None
        if kind == "backup":
            db = SessionLocal()
            try:
                job = db.get(BackupJob, entity_id)
                job_timeout = job.timeout_seconds if job else None
                job_name = job.name if job else str(entity_id)
            finally:
                db.close()

            raw = job_timeout if job_timeout is not None else settings.JOB_TIMEOUT_SECONDS
            timeout = raw if raw > 0 else None
        else:
            # Restore: use global default only (no per-record timeout field)
            raw = settings.JOB_TIMEOUT_SECONDS
            timeout = raw if raw > 0 else None
            job_name = f"restore-{entity_id}"

        target = _run_backup_entry if kind == "backup" else _run_restore_entry
        # spawn (not fork): forking a multithreaded process — uvicorn workers,
        # APScheduler, held locks — risks deadlocks in the child. spawn gives a
        # clean interpreter that rebuilds its own DB/Docker state.
        ctx = multiprocessing.get_context("spawn")
        worker = ctx.Process(target=target, args=(entity_id,), daemon=True)
        worker.start()
        worker.join(timeout)

        if worker.is_alive():
            # Exceeded its timeout. Because this is a separate process it can be
            # forcibly killed, so the concurrency slot is only released once the
            # worker is truly dead — no orphan can still be mutating containers.
            logger.error(
                "%s job %s timed out after %ds; terminating worker process",
                kind, job_name, timeout,
            )
            worker.terminate()
            worker.join(10)
            if worker.is_alive():
                worker.kill()
                worker.join()
            self._mark_incomplete(entity_id, kind, f"Job timed out after {timeout}s")
        elif worker.exitcode not in (0, None):
            # Worker died abnormally (crash/OOM/kill) without recording a result.
            logger.error(
                "%s job %s worker exited abnormally (code %s)",
                kind, job_name, worker.exitcode,
            )
            self._mark_incomplete(
                entity_id, kind, f"Worker process exited abnormally (code {worker.exitcode})"
            )

    def _mark_incomplete(self, entity_id: int, kind: str, message: str) -> None:
        """Mark a still-'running' record as failed when its worker did not finish."""
        from app.database import SessionLocal
        from app.models import BackupRecord
        from app.services.notification_service import notification_service

        db = SessionLocal()
        try:
            if kind == "backup":
                # Find the running record for this job and mark it failed
                record = (
                    db.query(BackupRecord)
                    .filter(BackupRecord.job_id == entity_id, BackupRecord.status == "running")
                    .order_by(BackupRecord.started_at.desc())
                    .first()
                )
                if record:
                    record.status = "error"
                    record.error_message = message
                    record.completed_at = datetime.now(timezone.utc)
                    db.commit()
                    job_name = record.job.name if record.job else str(entity_id)
                    self._restart_recorded_containers(record, job_name)
                    notification_service.notify_event("failure", job_name, message)
        except Exception as exc:
            logger.error("Failed to mark incomplete job: %s", exc)
        finally:
            db.close()

    @staticmethod
    def _restart_recorded_containers(record, job_name: str) -> None:
        """Start the containers a killed worker had stopped.

        The worker runs in a separate process so it can be forcibly terminated
        on timeout — which also means its own cleanup never runs. The containers
        it stopped are recorded before stopping precisely so the parent can
        bring them back here.
        """
        from app.services.docker_service import docker_service

        try:
            names = json.loads(record.containers_stopped or "[]")
        except (json.JSONDecodeError, TypeError):
            names = []
        if not names:
            return
        try:
            by_name = {c["name"]: c["id"] for c in docker_service.list_containers(all=True)}
            ids = [by_name[n] for n in names if n in by_name]
            started = docker_service.start_containers(ids)
            logger.info(
                "Restarted %d container(s) left stopped by terminated job '%s'",
                len(started), job_name,
            )
        except Exception as exc:
            logger.error(
                "Could not restart containers for terminated job '%s': %s", job_name, exc
            )

    def _run_backup(self, job_id: int) -> None:
        from app.database import SessionLocal
        from app.models import BackupJob, BackupRecord
        from app.services.docker_service import docker_service
        from app.services.storage_service import storage_service
        from app.services.notification_service import notification_service
        from app.config import settings

        db = SessionLocal()
        start_time = time.time()
        record = None
        stopped: list[str] = []
        archive_path: Path | None = None

        try:
            job = db.get(BackupJob, job_id)
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
            label_key = job.label_key or settings.DOCKER_LABEL_KEY
            label_value = job.label_value or job.name
            containers = docker_service.find_containers_by_label(label_key, label_value)
            container_ids = [c["id"] for c in containers]
            container_names = [c["name"] for c in containers]

            if not containers:
                raise RuntimeError(
                    f"No containers matched label '{label_key}={label_value}'. "
                    "Ensure your containers have the correct label set."
                )

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
                raise RuntimeError(
                    f"No volumes found on containers matched by '{label_key}={label_value}'. "
                    "Ensure the containers have named volumes attached."
                )

            # 3. Stop containers
            running_ids = [
                c["id"] for c in containers if c["status"] == "running"
            ]
            # Record which containers we are about to stop *before* stopping
            # them, so a crash mid-backup leaves a trail for startup recovery.
            record.containers_stopped = json.dumps(container_names)
            db.commit()

            stopped = docker_service.stop_containers(running_ids)
            stopped_names = [c["name"] for c in containers if c["id"] in set(stopped)]
            self._log(
                db, "info", job.name,
                f"Stopped {len(stopped)} container(s): {', '.join(stopped_names)}"
            )

            # 4. Export volumes via helper containers and create tar.gz
            temp_dir = settings.BACKUP_TEMP_DIR
            temp_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            archive_name = f"{job.name}_{timestamp}.tar.gz"
            archive_path = temp_dir / archive_name

            import tempfile
            exported_volumes: list[str] = []
            failed_volumes: list[str] = []
            # Stage under BACKUP_TEMP_DIR, not /tmp: the uncompressed copy of
            # every volume goes here and would otherwise fill the container's
            # writable layer instead of the volume provisioned for it.
            with tempfile.TemporaryDirectory(prefix="bb_", dir=str(temp_dir)) as work_dir:
                for vol in all_volumes:
                    exported = docker_service.export_volume(vol["name"], work_dir)
                    if exported:
                        exported_volumes.append(vol["name"])
                        logger.info("Exported volume %s to staging dir", vol["name"])
                    else:
                        failed_volumes.append(vol["name"])
                        self._log(db, "warning", job.name, f"Could not export volume {vol['name']}")

                if not exported_volumes:
                    raise RuntimeError(
                        "No volumes could be exported "
                        f"({len(failed_volumes)} failed) — refusing to record an empty backup"
                    )

                with tarfile.open(
                    str(archive_path), "w:gz", compresslevel=_compress_level(db)
                ) as tar:
                    for vol_name in exported_volumes:
                        vol_dir = os.path.join(work_dir, vol_name)
                        if os.path.isdir(vol_dir):
                            tar.add(vol_dir, arcname=vol_name)
                            logger.info("Added volume %s to archive", vol_name)

            archive_size = archive_path.stat().st_size if archive_path.exists() else 0

            # 5. Upload to storage
            storage = job.storage
            storage_config = json.loads(storage.config_json or "{}")
            remote_path = storage_service.upload(
                storage.type, storage_config, str(archive_path), archive_name
            )

            # 5b. Verify the uploaded object exists and matches the local size.
            # Without this a truncated transfer is still recorded as success.
            if _verify_backups_enabled(db):
                self._verify_upload(
                    db, job.name, storage.type, storage_config,
                    remote_path, archive_size,
                )

            # 6. Restart containers
            docker_service.start_containers(stopped)
            stopped = []
            self._log(
                db, "info", job.name,
                f"Restarted {len(stopped_names)} container(s)"
            )

            # 7. Update record
            duration = time.time() - start_time
            # A backup missing some of its volumes is not a clean success.
            record.status = "warning" if failed_volumes else "success"
            record.size_bytes = archive_size
            record.duration_seconds = round(duration, 2)
            # The temp archive is always removed in the finally block, so
            # file_path records where the archive actually lives (localfs moves
            # it to its final location; other backends leave nothing local).
            record.file_path = remote_path if storage.type == "localfs" else None
            record.storage_path = remote_path
            record.completed_at = datetime.now(timezone.utc)
            record.containers_stopped = json.dumps(container_names)
            record.volumes_backed_up = json.dumps(exported_volumes)
            if failed_volumes:
                record.error_message = (
                    f"Volumes not backed up: {', '.join(failed_volumes)}"
                )
            db.commit()

            size_str = self._format_size(archive_size)
            dur_str = f"{duration:.0f}s"
            if failed_volumes:
                self._log(
                    db, "warning", job.name,
                    f"Backup completed with {len(failed_volumes)} volume(s) missing",
                    f"Size: {size_str} | Duration: {dur_str} | Storage: {storage.name} | "
                    f"Failed: {', '.join(failed_volumes)}"
                )
                notification_service.notify_event(
                    "failure", job.name,
                    f"Backup incomplete — could not export: {', '.join(failed_volumes)}",
                )
            else:
                self._log(
                    db, "success", job.name,
                    "Backup completed successfully",
                    f"Size: {size_str} | Duration: {dur_str} | Storage: {storage.name}"
                )
                # 8. Notify
                notification_service.notify_event("success", job.name, f"Backup completed: {size_str}")

            # 9. Apply retention policy if one is linked to this job
            if job.retention_id:
                try:
                    from app.services.rotation_service import rotation_service
                    rotation_service.apply_policy(job.retention_id)
                    self._log(db, "info", job.name, "Retention policy applied after backup")
                except Exception as ret_exc:
                    logger.warning("Retention cleanup failed after backup: %s", ret_exc)
                    self._log(db, "warning", job.name, f"Retention cleanup failed: {ret_exc}")

        except Exception as exc:
            logger.exception("Backup job %d failed", job_id)
            # The failure may itself have been a DB error, which leaves the
            # session unusable — roll back before touching it again, otherwise
            # every statement below raises PendingRollbackError and the error
            # record is never written at all.
            try:
                db.rollback()
            except Exception as rb_exc:
                logger.warning("Rollback after backup failure failed: %s", rb_exc)

            job_name = "unknown"
            try:
                if record is not None:
                    record = db.get(BackupRecord, record.id)
                j = db.get(BackupJob, job_id)
                if j:
                    job_name = j.name
            except Exception:
                logger.debug("Could not resolve job name for job %d", job_id, exc_info=True)

            try:
                if record is not None:
                    record.status = "error"
                    record.error_message = str(exc)
                    record.completed_at = datetime.now(timezone.utc)
                    record.duration_seconds = round(time.time() - start_time, 2)
                    db.commit()
            except Exception as db_exc:
                logger.error("Could not write error record for job %d: %s", job_id, db_exc)

            # Logging and notifying must not be able to suppress the restart
            # of the user's containers in the finally block below.
            try:
                self._log(db, "error", job_name, f"Backup failed: {exc}")
            except Exception as log_exc:
                logger.error("Could not write failure log entry: %s", log_exc)
            try:
                notification_service.notify_event("failure", job_name, str(exc))
            except Exception as notify_exc:
                logger.error("Failure notification failed: %s", notify_exc)

        finally:
            # Restarting the user's containers is the one thing that must always
            # happen — a failure anywhere above must not leave them stopped.
            if stopped:
                try:
                    docker_service.start_containers(stopped)
                    logger.info("Restarted %d container(s) after backup failure", len(stopped))
                except Exception as restart_exc:
                    logger.error("Failed to restart containers after backup: %s", restart_exc)

            # Never leave the archive behind: a failed upload otherwise leaks a
            # full-size file every run until the temp volume is full.
            if archive_path is not None:
                try:
                    Path(archive_path).unlink(missing_ok=True)
                except Exception as cleanup_exc:
                    logger.warning("Could not remove temp archive %s: %s", archive_path, cleanup_exc)

            db.close()

    def _verify_upload(
        self, db, job_name: str, storage_type: str, storage_config: dict,
        remote_path: str, expected_size: int,
    ) -> None:
        """Confirm the uploaded object exists and matches the local archive size.

        Raises RuntimeError on mismatch so the record is not written as success.
        """
        from app.services.storage_service import storage_service

        remote_size = storage_service.remote_size(storage_type, storage_config, remote_path)
        if remote_size is None:
            # Backend cannot report a size — record the gap rather than
            # silently claiming the upload was verified.
            self._log(
                db, "warning", job_name,
                "Upload verification skipped: storage backend did not report a size",
            )
            return
        if remote_size != expected_size:
            raise RuntimeError(
                f"Upload verification failed: remote object is {remote_size} bytes, "
                f"expected {expected_size}"
            )
        self._log(
            db, "info", job_name,
            f"Upload verified: {self._format_size(remote_size)} on remote",
        )

    # ------------------------------------------------------------------
    # Restore execution
    # ------------------------------------------------------------------

    def _run_restore(self, backup_id: int) -> None:
        from app.database import SessionLocal
        from app.models import BackupRecord
        from app.services.docker_service import docker_service
        from app.services.storage_service import storage_service
        from app.services.notification_service import notification_service
        from app.config import settings

        db = SessionLocal()
        stopped: list[str] = []
        local_archive: Path | None = None
        job_name = "System"

        try:
            record = db.get(BackupRecord, backup_id)
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
            label_key = getattr(job, "label_key", None) or settings.DOCKER_LABEL_KEY
            label_value = getattr(job, "label_value", None) or job_name
            containers = docker_service.find_containers_by_label(label_key, label_value)
            running_ids = [c["id"] for c in containers if c["status"] == "running"]
            stopped = docker_service.stop_containers(running_ids)

            # 3. Extract archive and import into volumes via helper containers
            import tempfile
            from app.services.tar_utils import safe_extractall
            with tempfile.TemporaryDirectory(prefix="bb_restore_", dir=str(temp_dir)) as work_dir:
                with tarfile.open(str(local_archive), "r:gz") as tar:
                    safe_extractall(tar, work_dir)

                # Each top-level dir in the archive is a volume name
                volume_names = [
                    d for d in os.listdir(work_dir)
                    if os.path.isdir(os.path.join(work_dir, d))
                ]

                # Only restore volumes this record actually backed up. Without
                # this, a crafted or corrupt archive can name any volume on the
                # host and import_volume will wipe it.
                # Records created by discovery (POST /api/backups/import) have
                # no recorded volume list, so there is nothing to scope against
                # and the archive's own directories are used as-is.
                expected = set(json.loads(record.volumes_backed_up or "[]"))
                if expected:
                    unexpected = [v for v in volume_names if v not in expected]
                    if unexpected:
                        self._log(
                            db, "warning", job_name,
                            "Skipping volume(s) not listed in this backup record: "
                            f"{', '.join(unexpected)}",
                        )
                    volume_names = [v for v in volume_names if v in expected]

                if not volume_names:
                    raise RuntimeError(
                        "Archive contains no volumes matching this backup record"
                    )

                failed_volumes = []
                for vol_name in volume_names:
                    vol_dir = os.path.join(work_dir, vol_name)
                    ok = docker_service.import_volume(vol_name, vol_dir)
                    if ok:
                        logger.info("Restored volume %s", vol_name)
                    else:
                        logger.warning("Failed to restore volume %s", vol_name)
                        failed_volumes.append(vol_name)

            if failed_volumes:
                msg = f"Restore partially failed: could not import volumes: {', '.join(failed_volumes)}"
                self._log(db, "warning", job_name, msg)
                notification_service.notify_event("failure", job_name, msg)
            else:
                self._log(db, "success", job_name, f"Restore completed from backup #{backup_id}")
                notification_service.notify_event("success", job_name, f"Restore completed from backup #{backup_id}")

        except Exception as exc:
            logger.exception("Restore from backup %d failed", backup_id)
            try:
                db.rollback()
            except Exception as rb_exc:
                logger.warning("Rollback after restore failure failed: %s", rb_exc)
            try:
                self._log(db, "error", job_name, f"Restore failed: {exc}")
            except Exception as log_exc:
                logger.error("Could not write restore failure log: %s", log_exc)
            try:
                notification_service.notify_event("failure", job_name, f"Restore failed: {exc}")
            except Exception as notify_exc:
                logger.error("Restore failure notification failed: %s", notify_exc)
        finally:
            # Containers must come back up even if the restore failed partway.
            if stopped:
                try:
                    docker_service.start_containers(stopped)
                    logger.info("Restarted %d container(s) after restore", len(stopped))
                except Exception as restart_exc:
                    logger.error("Failed to restart containers after restore: %s", restart_exc)

            if local_archive is not None:
                try:
                    Path(local_archive).unlink(missing_ok=True)
                except Exception as cleanup_exc:
                    logger.warning("Could not remove restore archive: %s", cleanup_exc)

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
