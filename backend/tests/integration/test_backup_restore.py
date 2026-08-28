"""Backup and restore across every storage backend, against real Docker volumes.

Each test creates real volumes with known contents, runs a real backup through
the real storage backend, destroys the data, restores, and compares the volume
contents byte for byte. A test only passes if the data actually survived the
round trip.
"""

from __future__ import annotations

import json

import pytest

from .harness import WORKLOAD_IMAGE

LABEL_KEY = "dvbm.job"


def run_backup(job_id: int):
    """Run a backup synchronously and return its BackupRecord."""
    from app.database import SessionLocal
    from app.models import BackupRecord
    from app.services.backup_service import backup_service

    backup_service._run_backup(job_id)

    session = SessionLocal()
    try:
        return (
            session.query(BackupRecord)
            .filter(BackupRecord.job_id == job_id)
            .order_by(BackupRecord.id.desc())
            .first()
        )
    finally:
        session.close()


def run_restore(backup_id: int):
    from app.services.backup_service import backup_service

    backup_service._run_restore(backup_id)


# ----------------------------------------------------------------------
# The four backends, as (fixture name, storage type) pairs
# ----------------------------------------------------------------------

BACKENDS = [
    pytest.param("localfs_config", "localfs", id="localfs"),
    pytest.param("minio_config", "s3", id="s3"),
    pytest.param("sftp_config", "ftp", id="sftp"),
    pytest.param("rclone_config", "rclone", id="rclone"),
]


@pytest.mark.parametrize("config_fixture,storage_type", BACKENDS)
def test_backup_and_restore_roundtrip(
    request, env, make_storage, make_job, config_fixture, storage_type
):
    """Data written to a volume survives a full backup/restore cycle.

    This is the test that matters most: it destroys the original data between
    the backup and the restore, so passing requires the archive to genuinely
    contain it.
    """
    storage_config = request.getfixturevalue(config_fixture)
    job_name = f"roundtrip-{storage_type}-{env.run_id}"

    original = {
        "config.yml": "setting: value\n",
        "data/records.txt": "row one\nrow two\n",
        "data/nested/deep.bin": "x" * 4096,
    }
    volume = env.create_volume(f"{storage_type}-vol", original)
    env.create_workload(
        f"{storage_type}-app",
        volumes={volume: "/data"},
        labels={LABEL_KEY: job_name},
    )

    storage = make_storage(f"store-{storage_type}-{env.run_id}", storage_type, storage_config)
    job = make_job(job_name, storage, LABEL_KEY, job_name)

    record = run_backup(job.id)
    assert record is not None, "no backup record was written"
    assert record.status == "success", f"backup failed: {record.error_message}"
    assert record.size_bytes and record.size_bytes > 0
    assert json.loads(record.volumes_backed_up) == [volume]
    assert record.storage_path, "no remote path recorded"

    # Destroy the data so a restore that does nothing cannot pass.
    env.client.containers.run(
        WORKLOAD_IMAGE,
        command=["sh", "-c", "rm -rf /data/* /data/.[!.]* 2>/dev/null; true"],
        volumes={volume: {"bind": "/data", "mode": "rw"}},
        remove=True,
    )
    assert env.read_volume(volume) == {}, "volume was not emptied by the test setup"

    run_restore(record.id)

    restored = env.read_volume(volume)
    assert restored == original, (
        "restored volume does not match the original\n"
        f"missing: {set(original) - set(restored)}\n"
        f"unexpected: {set(restored) - set(original)}"
    )


@pytest.mark.parametrize("config_fixture,storage_type", BACKENDS)
def test_upload_is_verified_against_remote(
    request, env, make_storage, make_job, config_fixture, storage_type
):
    """remote_size() reports the real object size for every backend.

    This is what upload verification depends on; a backend that cannot report
    a size silently skips verification, so it is worth asserting directly.
    """
    from app.services.storage_service import storage_service

    storage_config = request.getfixturevalue(config_fixture)
    job_name = f"verify-{storage_type}-{env.run_id}"

    volume = env.create_volume(f"{storage_type}-vvol", {"f.txt": "content" * 100})
    env.create_workload(
        f"{storage_type}-vapp",
        volumes={volume: "/data"},
        labels={LABEL_KEY: job_name},
    )

    storage = make_storage(f"vstore-{storage_type}-{env.run_id}", storage_type, storage_config)
    job = make_job(job_name, storage, LABEL_KEY, job_name)

    record = run_backup(job.id)
    assert record.status == "success", f"backup failed: {record.error_message}"

    remote_size = storage_service.remote_size(
        storage_type, storage_config, record.storage_path
    )
    assert remote_size is not None, (
        f"{storage_type} could not report a remote size, so uploads are never verified"
    )
    assert remote_size == record.size_bytes, (
        f"remote object is {remote_size} bytes, record says {record.size_bytes}"
    )


@pytest.mark.parametrize("config_fixture,storage_type", BACKENDS)
def test_delete_remote_removes_the_object(
    request, env, make_storage, make_job, config_fixture, storage_type
):
    """Retention's delete path actually removes the file from the backend."""
    from app.services.storage_service import storage_service

    storage_config = request.getfixturevalue(config_fixture)
    job_name = f"delete-{storage_type}-{env.run_id}"

    volume = env.create_volume(f"{storage_type}-dvol", {"f.txt": "data"})
    env.create_workload(
        f"{storage_type}-dapp",
        volumes={volume: "/data"},
        labels={LABEL_KEY: job_name},
    )
    storage = make_storage(f"dstore-{storage_type}-{env.run_id}", storage_type, storage_config)
    job = make_job(job_name, storage, LABEL_KEY, job_name)

    record = run_backup(job.id)
    assert record.status == "success"

    storage_service.delete_remote(storage_type, storage_config, record.storage_path)

    assert storage_service.remote_size(
        storage_type, storage_config, record.storage_path
    ) is None, "object still present after delete_remote"


def test_multiple_volumes_are_all_captured(env, make_storage, make_job, localfs_config):
    """A container with several volumes gets all of them, keyed by volume name."""
    job_name = f"multivol-{env.run_id}"

    vol_a = env.create_volume("multi-a", {"a.txt": "alpha"})
    vol_b = env.create_volume("multi-b", {"b.txt": "bravo"})
    env.create_workload(
        "multi-app",
        volumes={vol_a: "/data/a", vol_b: "/data/b"},
        labels={LABEL_KEY: job_name},
    )

    storage = make_storage(f"multi-store-{env.run_id}", "localfs", localfs_config)
    job = make_job(job_name, storage, LABEL_KEY, job_name)

    record = run_backup(job.id)
    assert record.status == "success", record.error_message
    assert set(json.loads(record.volumes_backed_up)) == {vol_a, vol_b}

    # Wipe both, restore, and confirm each volume got its own contents back
    # rather than the two being merged.
    for vol in (vol_a, vol_b):
        env.client.containers.run(
            WORKLOAD_IMAGE,
            command=["sh", "-c", "rm -rf /data/* 2>/dev/null; true"],
            volumes={vol: {"bind": "/data", "mode": "rw"}},
            remove=True,
        )

    run_restore(record.id)

    assert env.read_volume(vol_a) == {"a.txt": "alpha"}
    assert env.read_volume(vol_b) == {"b.txt": "bravo"}


def test_shared_volume_is_deduplicated(env, make_storage, make_job, localfs_config):
    """Two containers sharing a volume back it up once, not twice."""
    job_name = f"shared-{env.run_id}"

    shared = env.create_volume("shared-vol", {"s.txt": "shared"})
    env.create_workload(
        "shared-app1",
        volumes={shared: "/data"},
        labels={LABEL_KEY: job_name},
    )
    env.create_workload(
        "shared-app2",
        volumes={shared: "/data"},
        labels={LABEL_KEY: job_name},
    )

    storage = make_storage(f"shared-store-{env.run_id}", "localfs", localfs_config)
    job = make_job(job_name, storage, LABEL_KEY, job_name)

    record = run_backup(job.id)
    assert record.status == "success", record.error_message
    assert json.loads(record.volumes_backed_up) == [shared]


@pytest.mark.slow
def test_large_volume_streams_without_buffering(
    env, make_storage, make_job, localfs_config
):
    """A volume larger than a trivial size round-trips intact.

    Export and import stream through spooled temp files rather than holding the
    archive in memory; this exercises that path with real data.
    """
    job_name = f"largevol-{env.run_id}"
    # 64 files x 512 KB = 32 MB, large enough to be a real stream but quick.
    contents = {f"blob_{i:02d}.bin": (f"{i:03d}" * 170)[:512] * 1024 for i in range(64)}

    volume = env.create_volume("large-vol", contents)
    env.create_workload(
        "large-app",
        volumes={volume: "/data"},
        labels={LABEL_KEY: job_name},
    )
    storage = make_storage(f"large-store-{env.run_id}", "localfs", localfs_config)
    job = make_job(job_name, storage, LABEL_KEY, job_name)

    record = run_backup(job.id)
    assert record.status == "success", record.error_message

    env.client.containers.run(
        WORKLOAD_IMAGE,
        command=["sh", "-c", "rm -rf /data/* 2>/dev/null; true"],
        volumes={volume: {"bind": "/data", "mode": "rw"}},
        remove=True,
    )
    run_restore(record.id)

    restored = env.read_volume(volume)
    assert len(restored) == len(contents)
    assert restored == contents
