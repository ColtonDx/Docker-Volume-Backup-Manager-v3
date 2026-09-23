"""Retention arithmetic, against a real in-memory-ish database but no Docker.

Retention is the only part of the app that deliberately deletes backups, so the
edge cases matter more here than anywhere else.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@pytest.fixture
def retention_db(tmp_path, monkeypatch):
    """A throwaway database, isolated from any real deployment."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("BACKUP_TEMP_DIR", str(tmp_path / "temp"))
    monkeypatch.delenv("DB_ENCRYPTION_KEY", raising=False)

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.database import Base
    from app import models  # noqa: F401 — registers the tables

    engine = create_engine(f"sqlite:///{tmp_path / 'retention.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def seed(session, *, min_backups, max_backups, ages_days, retention_days=30):
    """Create a policy, a job and one success record per age in *ages_days*."""
    from app.models import BackupJob, BackupRecord, RetentionPolicy, StorageBackend

    storage = StorageBackend(
        name=f"s-{min_backups}-{max_backups}-{len(ages_days)}",
        type="localfs",
        config_json=json.dumps({"path": "/local-backups"}),
    )
    session.add(storage)
    session.commit()

    policy = RetentionPolicy(
        name=f"p-{min_backups}-{max_backups}-{len(ages_days)}",
        retention_days=retention_days,
        min_backups=min_backups,
        max_backups=max_backups,
    )
    session.add(policy)
    session.commit()

    job = BackupJob(
        name=f"j-{policy.id}",
        storage_id=storage.id,
        retention_id=policy.id,
        label_key="dvbm.job",
        label_value="x",
    )
    session.add(job)
    session.commit()

    now = datetime.now(timezone.utc)
    for age in ages_days:
        session.add(BackupRecord(
            job_id=job.id,
            status="success",
            started_at=now - timedelta(days=age),
            size_bytes=100,
            # No storage_path: nothing to delete remotely, so these tests
            # exercise the selection logic in isolation.
            storage_path=None,
        ))
    session.commit()
    return policy, job


def remaining(session, job_id) -> int:
    from app.models import BackupRecord

    return session.query(BackupRecord).filter(BackupRecord.job_id == job_id).count()


def apply(session, policy_id, monkeypatch):
    """Run the retention service against this test's session."""
    from app.services.rotation_service import rotation_service

    monkeypatch.setattr(
        "app.database.SessionLocal", lambda: session, raising=False
    )
    # rotation_service closes the session it is given; keep it usable afterwards.
    monkeypatch.setattr(session, "close", lambda: None, raising=False)
    return rotation_service.apply_policy(policy_id)


def test_last_backup_is_never_deleted(retention_db, monkeypatch):
    """Even with everything expired and min_backups=0, one record survives.

    min_backups=0 is set directly on the row here, bypassing schema validation,
    to represent a policy created before that validation existed.
    """
    policy, job = seed(
        retention_db, min_backups=0, max_backups=None, ages_days=[90, 80, 70, 60, 50]
    )
    apply(retention_db, policy.id, monkeypatch)

    assert remaining(retention_db, job.id) >= 1, (
        "retention deleted every backup the job had"
    )


def test_min_backups_is_respected_when_all_are_expired(retention_db, monkeypatch):
    policy, job = seed(
        retention_db, min_backups=3, max_backups=None, ages_days=[90, 80, 70, 60, 50]
    )
    apply(retention_db, policy.id, monkeypatch)

    assert remaining(retention_db, job.id) == 3


def test_records_inside_the_window_are_kept(retention_db, monkeypatch):
    """Nothing within retention_days is deleted."""
    policy, job = seed(
        retention_db,
        min_backups=1,
        max_backups=None,
        ages_days=[1, 2, 3, 4, 5],
        retention_days=30,
    )
    apply(retention_db, policy.id, monkeypatch)

    assert remaining(retention_db, job.id) == 5


def test_expired_records_beyond_the_floor_are_deleted(retention_db, monkeypatch):
    policy, job = seed(
        retention_db,
        min_backups=2,
        max_backups=None,
        ages_days=[1, 2, 90, 91, 92],
        retention_days=30,
    )
    apply(retention_db, policy.id, monkeypatch)

    # The two recent ones are in-window; the floor covers the newest two
    # overall, so the three expired records beyond it go.
    assert remaining(retention_db, job.id) == 2


def test_max_backups_trims_to_the_limit(retention_db, monkeypatch):
    """Count-based trimming applies even when everything is in-window."""
    policy, job = seed(
        retention_db,
        min_backups=1,
        max_backups=3,
        ages_days=[1, 2, 3, 4, 5, 6],
        retention_days=365,
    )
    apply(retention_db, policy.id, monkeypatch)

    assert remaining(retention_db, job.id) == 3


def test_min_backups_wins_over_a_lower_max(retention_db, monkeypatch):
    """A contradictory policy keeps data rather than deleting it.

    min_backups=5 with max_backups=3 is a misconfiguration; the safe reading is
    to honour the floor.
    """
    policy, job = seed(
        retention_db,
        min_backups=5,
        max_backups=3,
        ages_days=[10, 20, 30, 40, 50, 60, 70],
        retention_days=1,
    )
    apply(retention_db, policy.id, monkeypatch)

    assert remaining(retention_db, job.id) >= 5, (
        "min_backups floor was violated by a smaller max_backups"
    )


def test_failed_records_are_not_counted_or_deleted(retention_db, monkeypatch):
    """Retention only considers successful backups."""
    from app.models import BackupRecord

    policy, job = seed(
        retention_db, min_backups=1, max_backups=None, ages_days=[90, 91], retention_days=30
    )
    retention_db.add(BackupRecord(
        job_id=job.id,
        status="error",
        started_at=datetime.now(timezone.utc) - timedelta(days=95),
        error_message="failed",
    ))
    retention_db.commit()

    apply(retention_db, policy.id, monkeypatch)

    errors = (
        retention_db.query(BackupRecord)
        .filter(BackupRecord.job_id == job.id, BackupRecord.status == "error")
        .count()
    )
    assert errors == 1, "retention deleted a failed record it should ignore"


def test_record_is_kept_when_the_remote_delete_fails(retention_db, monkeypatch):
    """A failed storage delete must not orphan the file.

    Dropping the row while the object survives leaves a file nothing points at,
    invisible to the UI and never retried.
    """
    from app.models import BackupRecord

    policy, job = seed(
        retention_db, min_backups=1, max_backups=None, ages_days=[90, 91, 92], retention_days=30
    )
    # Give the records a remote path so the delete path is exercised.
    for rec in retention_db.query(BackupRecord).filter(BackupRecord.job_id == job.id):
        rec.storage_path = f"/local-backups/{rec.id}.tar.gz"
    retention_db.commit()

    def always_fails(*args, **kwargs):
        raise RuntimeError("storage backend unreachable")

    monkeypatch.setattr(
        "app.services.storage_service.storage_service.delete_remote", always_fails
    )

    apply(retention_db, policy.id, monkeypatch)

    assert remaining(retention_db, job.id) == 3, (
        "records were deleted from the database even though the remote delete failed"
    )
