"""Fixtures for the integration suite.

Each test module gets its own isolated app instance: a fresh SQLite database in
a temp directory, with settings pointed at that directory, so tests never touch
a real deployment's data.
"""

from __future__ import annotations

import json
import os
import uuid

import pytest

from .harness import (
    MINIO_IMAGE,
    SFTP_IMAGE,
    TestEnv,
    WORKLOAD_IMAGE,
    docker_available,
    ensure_images,
    rclone_available,
)

_available, _reason = docker_available()

# Applies to every test in this package.
pytestmark = pytest.mark.integration


def pytest_collection_modifyitems(config, items):
    """Skip the whole integration package when Docker is unreachable."""
    if _available:
        return
    skip = pytest.mark.skip(reason=f"Docker daemon not available: {_reason}")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def docker_client():
    if not _available:
        pytest.skip(f"Docker not available: {_reason}")
    import docker

    client = docker.from_env()
    yield client
    client.close()


@pytest.fixture(scope="session", autouse=True)
def _images(docker_client):
    """Make sure the images the suite needs are present before any test runs."""
    # The app pulls its own alpine helper image; include it so the first
    # backup does not pay for that pull mid-test.
    ensure_images(docker_client, [WORKLOAD_IMAGE, "alpine:3.20"])
    return True


@pytest.fixture(scope="session")
def run_id() -> str:
    """Short id shared by every resource in this pytest run."""
    return uuid.uuid4().hex[:8]


@pytest.fixture(scope="session")
def app_env(tmp_path_factory, run_id):
    """Configure the application to use a throwaway data directory.

    Environment variables must be set before `app.config` is imported, because
    Settings reads them at class-definition time. The app modules are then
    imported once and reused for the whole session.
    """
    # DATA_DIR / BACKUP_TEMP_DIR are set by the top-level tests/conftest.py
    # before any application module is imported; Settings reads them at import
    # time, so re-pointing them here would have no effect on the live config.
    from app.config import settings

    data_dir = settings.DATA_DIR
    temp_dir = settings.BACKUP_TEMP_DIR
    local_backups = tmp_path_factory.mktemp("dvbm-local")
    data_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("MAX_CONCURRENT_BACKUPS", "1")
    os.environ.setdefault("JOB_TIMEOUT_SECONDS", "300")

    from app import database
    from app.services import storage_service as storage_module

    database.init_db()

    # Local filesystem backends are confined to an allowlist of roots; point
    # that at the temp directory for the duration of the suite.
    storage_module.StorageService.LOCALFS_ROOTS = (
        str(local_backups),
        str(temp_dir),
    )

    return {
        "data_dir": data_dir,
        "temp_dir": temp_dir,
        "local_backups": local_backups,
    }


@pytest.fixture
def db(app_env):
    """A database session that is closed after the test."""
    from app.database import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def env(docker_client, run_id, tmp_path, request):
    """A disposable Docker environment, torn down after each test.

    The id combines the session run id with a per-test suffix so container and
    volume names — and therefore the dvbm labels derived from them — are unique
    to this test. Without that, a leftover container from an interrupted run
    could still carry a matching label and silently join a later backup.
    """
    test_id = uuid.uuid4().hex[:6]
    environment = TestEnv(
        client=docker_client,
        run_id=f"{run_id}{test_id}",
        tmp_path=tmp_path,
    )
    try:
        yield environment
    finally:
        environment.cleanup()


@pytest.fixture
def unique_label(env):
    """A dvbm label value that no other test or stale container can match."""
    return f"job-{env.run_id}"


# ----------------------------------------------------------------------
# Storage backends
#
# Session-scoped because starting MinIO and SFTP is the slow part; the tests
# that use them write to distinct keys/paths so sharing is safe.
# ----------------------------------------------------------------------

@pytest.fixture(scope="session")
def shared_env(docker_client, run_id, tmp_path_factory):
    env = TestEnv(
        client=docker_client,
        run_id=run_id,
        tmp_path=tmp_path_factory.mktemp("shared"),
    )
    try:
        yield env
    finally:
        env.cleanup()


@pytest.fixture(scope="session")
def minio_config(shared_env, docker_client):
    try:
        ensure_images(docker_client, [MINIO_IMAGE])
        return shared_env.start_minio()
    except Exception as exc:
        pytest.skip(f"Could not start MinIO: {exc}")


@pytest.fixture(scope="session")
def sftp_config(shared_env, docker_client):
    try:
        ensure_images(docker_client, [SFTP_IMAGE])
        return shared_env.start_sftp()
    except Exception as exc:
        pytest.skip(f"Could not start SFTP server: {exc}")


@pytest.fixture(scope="session")
def rclone_config(shared_env, minio_config, app_env):
    if not rclone_available():
        pytest.skip("rclone binary not found on PATH")

    config_path, storage_config = shared_env.write_rclone_config(minio_config)

    from app.config import settings

    previous = settings.RCLONE_CONFIG
    settings.RCLONE_CONFIG = config_path
    yield storage_config
    settings.RCLONE_CONFIG = previous


@pytest.fixture
def localfs_config(app_env):
    return {"path": str(app_env["local_backups"])}


# Rows created by the factories below, cleaned up in dependency order by the
# _cleanup_rows fixture. PRAGMA foreign_keys is ON, so order matters:
# records -> jobs -> storages.
_pending_jobs: list = []
_pending_storages: list = []


@pytest.fixture(autouse=True)
def _cleanup_rows(db):
    """Remove rows created during a test, respecting foreign keys."""
    yield

    from app.models import BackupRecord

    try:
        for job in _pending_jobs:
            db.query(BackupRecord).filter(
                BackupRecord.job_id == job.id
            ).delete(synchronize_session=False)
        db.commit()

        for job in _pending_jobs:
            db.delete(job)
        db.commit()

        for storage in _pending_storages:
            db.delete(storage)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        _pending_jobs.clear()
        _pending_storages.clear()


@pytest.fixture
def make_storage(db):
    """Factory that persists a StorageBackend row and returns it."""
    from app.models import StorageBackend

    created = []

    def _make(name: str, backend_type: str, config: dict):
        row = StorageBackend(
            name=name,
            type=backend_type,
            config_json=json.dumps(config),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        created.append(row)
        return row

    yield _make

    # Storage rows are removed by the cleanup fixture, after the jobs that
    # reference them (foreign keys are enforced).
    _pending_storages.extend(created)


@pytest.fixture
def make_job(db):
    """Factory that persists a BackupJob row and returns it."""
    from app.models import BackupJob

    created = []

    def _make(name: str, storage, label_key: str, label_value: str, **kwargs):
        row = BackupJob(
            name=name,
            storage_id=storage.id,
            label_key=label_key,
            label_value=label_value,
            **kwargs,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        created.append(row)
        return row

    yield _make

    _pending_jobs.extend(created)
