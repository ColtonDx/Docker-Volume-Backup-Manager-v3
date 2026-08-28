"""Data integrity: the failure modes that previously produced silent data loss.

Each test here corresponds to a real defect. They exist to make sure a backup
that reports success can actually be restored, and that a backup that cannot be
restored never reports success.
"""

from __future__ import annotations

import json
import tarfile
from pathlib import Path
from unittest.mock import patch

import pytest

from .harness import WORKLOAD_IMAGE
from .test_backup_restore import LABEL_KEY, run_backup, run_restore

pytestmark = pytest.mark.integration


def test_total_export_failure_is_not_recorded_as_success(
    env, make_storage, make_job, localfs_config
):
    """When no volume can be exported, the job fails.

    Previously this produced a valid ~100 byte archive, a nonzero size, and a
    "success" record that the Restore page would happily offer.
    """
    from app.services import docker_service as docker_module

    job_name = f"allfail-{env.run_id}"
    vol = env.create_volume("allfail-vol", {"f.txt": "data"})
    env.create_workload(
        "allfail-app", volumes={vol: "/data"}, labels={LABEL_KEY: job_name}
    )

    storage = make_storage(f"allfail-store-{env.run_id}", "localfs", localfs_config)
    job = make_job(job_name, storage, LABEL_KEY, job_name)

    with patch.object(
        docker_module.docker_service, "export_volume", return_value=None
    ):
        record = run_backup(job.id)

    assert record.status == "error", (
        f"a backup with zero exported volumes reported {record.status!r}"
    )
    assert "no volumes could be exported" in (record.error_message or "").lower()


def test_partial_export_failure_is_recorded_as_warning(
    env, make_storage, make_job, localfs_config
):
    """When some volumes fail, the record says so and lists only what was saved."""
    from app.services import docker_service as docker_module

    job_name = f"partial-{env.run_id}"
    vol_ok = env.create_volume("partial-ok", {"good.txt": "saved"})
    vol_bad = env.create_volume("partial-bad", {"bad.txt": "lost"})
    env.create_workload(
        "partial-app",
        volumes={vol_ok: "/data/ok", vol_bad: "/data/bad"},
        labels={LABEL_KEY: job_name},
    )

    storage = make_storage(f"partial-store-{env.run_id}", "localfs", localfs_config)
    job = make_job(job_name, storage, LABEL_KEY, job_name)

    real_export = docker_module.docker_service.export_volume

    def flaky_export(volume_name, dest_dir):
        if volume_name == vol_bad:
            return None
        return real_export(volume_name, dest_dir)

    with patch.object(
        docker_module.docker_service, "export_volume", side_effect=flaky_export
    ):
        record = run_backup(job.id)

    assert record.status == "warning", (
        f"a backup missing a volume reported {record.status!r}, not 'warning'"
    )
    assert json.loads(record.volumes_backed_up) == [vol_ok]
    assert vol_bad in (record.error_message or "")


def test_failed_export_does_not_leave_an_empty_directory(
    env, make_storage, make_job, localfs_config
):
    """A volume that fails to export contributes nothing to the archive.

    export_volume creates its output directory before attempting the export, so
    a failure used to leave an empty directory that was indistinguishable from
    a genuinely empty volume.
    """
    from app.services import docker_service as docker_module

    job_name = f"emptydir-{env.run_id}"
    vol_ok = env.create_volume("emptydir-ok", {"good.txt": "saved"})
    vol_bad = env.create_volume("emptydir-bad", {"bad.txt": "lost"})
    env.create_workload(
        "emptydir-app",
        volumes={vol_ok: "/data/ok", vol_bad: "/data/bad"},
        labels={LABEL_KEY: job_name},
    )
    storage = make_storage(f"emptydir-store-{env.run_id}", "localfs", localfs_config)
    job = make_job(job_name, storage, LABEL_KEY, job_name)

    real_export = docker_module.docker_service.export_volume

    def flaky_export(volume_name, dest_dir):
        if volume_name == vol_bad:
            # Mimic a real failure: the helper container errors after the
            # output directory has already been created.
            import os

            os.makedirs(os.path.join(dest_dir, volume_name), exist_ok=True)
            raise RuntimeError("simulated docker failure")
        return real_export(volume_name, dest_dir)

    with patch.object(
        docker_module.docker_service, "export_volume", side_effect=flaky_export
    ):
        record = run_backup(job.id)

    # Whatever the outcome, the failed volume must not appear in the archive.
    archive = Path(record.storage_path) if record.storage_path else None
    if archive and archive.exists():
        with tarfile.open(archive) as tar:
            top_level = {n.split("/")[0] for n in tar.getnames() if n.strip("./")}
        assert vol_bad not in top_level, (
            "a volume that failed to export appears in the archive"
        )


def test_truncated_upload_is_caught_by_verification(
    env, make_storage, make_job, localfs_config
):
    """A remote object that does not match the local archive fails the backup."""
    from app.services import storage_service as storage_module

    job_name = f"truncated-{env.run_id}"
    vol = env.create_volume("truncated-vol", {"f.txt": "data" * 500})
    env.create_workload(
        "truncated-app", volumes={vol: "/data"}, labels={LABEL_KEY: job_name}
    )
    storage = make_storage(f"trunc-store-{env.run_id}", "localfs", localfs_config)
    job = make_job(job_name, storage, LABEL_KEY, job_name)

    # Patch the handler registry, which is what dispatch actually calls —
    # patching the class attribute has no effect, since the registry captured
    # the function object at import time.
    handlers = storage_module._HANDLERS["localfs"]
    original = handlers["size"]
    handlers["size"] = lambda config, path: 12
    try:
        record = run_backup(job.id)
    finally:
        handlers["size"] = original

    assert record.status == "error", (
        f"a truncated upload reported {record.status!r}"
    )
    assert "verification failed" in (record.error_message or "").lower()


def test_restore_ignores_volumes_not_in_the_record(
    env, make_storage, make_job, localfs_config
):
    """A volume named in the archive but not on the record is not restored.

    import_volume clears the target volume before writing, so honouring an
    arbitrary directory name in the archive would let a tampered or corrupt
    archive wipe an unrelated volume.
    """
    job_name = f"scoped-{env.run_id}"

    vol = env.create_volume("scoped-vol", {"mine.txt": "backed up"})
    bystander = env.create_volume("scoped-bystander", {"precious.txt": "do not touch"})
    env.create_workload(
        "scoped-app", volumes={vol: "/data"}, labels={LABEL_KEY: job_name}
    )
    storage = make_storage(f"scoped-store-{env.run_id}", "localfs", localfs_config)
    job = make_job(job_name, storage, LABEL_KEY, job_name)

    record = run_backup(job.id)
    assert record.status == "success", record.error_message

    # Rewrite the archive so it also contains a directory named after the
    # bystander volume — the shape of a tampered or mislabelled archive.
    archive = Path(record.storage_path)
    extract_dir = env.tmp_path / "repack"
    extract_dir.mkdir(exist_ok=True)
    with tarfile.open(archive) as tar:
        tar.extractall(extract_dir, filter="data")

    injected = extract_dir / bystander
    injected.mkdir(parents=True, exist_ok=True)
    (injected / "malicious.txt").write_text("should never be written")

    with tarfile.open(archive, "w:gz") as tar:
        for child in extract_dir.iterdir():
            tar.add(child, arcname=child.name)

    run_restore(record.id)

    assert env.read_volume(bystander) == {"precious.txt": "do not touch"}, (
        "restore wrote into a volume that was not part of the backup record"
    )
    assert env.read_volume(vol) == {"mine.txt": "backed up"}


def test_restore_rejects_path_traversal_in_archive(
    env, make_storage, make_job, localfs_config, tmp_path
):
    """An archive containing ../ members does not escape the staging directory."""
    job_name = f"traversal-{env.run_id}"

    vol = env.create_volume("traversal-vol", {"f.txt": "data"})
    env.create_workload(
        "traversal-app", volumes={vol: "/data"}, labels={LABEL_KEY: job_name}
    )
    storage = make_storage(f"trav-store-{env.run_id}", "localfs", localfs_config)
    job = make_job(job_name, storage, LABEL_KEY, job_name)

    record = run_backup(job.id)
    assert record.status == "success", record.error_message

    # Repack with a traversal member alongside the legitimate volume dir.
    archive = Path(record.storage_path)
    extract_dir = env.tmp_path / "trav"
    extract_dir.mkdir(exist_ok=True)
    with tarfile.open(archive) as tar:
        tar.extractall(extract_dir, filter="data")

    payload = tmp_path / "payload.txt"
    payload.write_text("escaped")
    canary = Path("/tmp") / f"dvbm-traversal-canary-{env.run_id}"
    if canary.exists():
        canary.unlink()

    with tarfile.open(archive, "w:gz") as tar:
        for child in extract_dir.iterdir():
            tar.add(child, arcname=child.name)
        tar.add(payload, arcname=f"../../../../../..{canary}")

    # The restore may fail; what matters is that nothing was written outside.
    try:
        run_restore(record.id)
    except Exception:
        pass

    assert not canary.exists(), (
        f"path traversal in a restore archive wrote to {canary}"
    )


def test_extraction_helper_rejects_escaping_members(tmp_path):
    """_extract_safely refuses members that resolve outside the destination.

    Asserted directly rather than only through a restore, because the tarfile
    default filter differs by Python version: 3.14 rejects these on its own,
    while 3.12 — which the shipped image uses — does not. Testing the helper
    keeps this meaningful on every interpreter.
    """
    from app.services.tar_utils import safe_extractall as _extract_safely

    payload = tmp_path / "payload.txt"
    payload.write_text("escaped")

    archive = tmp_path / "evil.tar"
    with tarfile.open(archive, "w") as tar:
        tar.add(payload, arcname="../escaped.txt")
        tar.add(payload, arcname="/absolute.txt")

    dest = tmp_path / "dest"
    dest.mkdir()

    with pytest.raises(Exception):
        with tarfile.open(archive) as tar:
            _extract_safely(tar, str(dest))

    assert not (tmp_path / "escaped.txt").exists(), "member escaped the destination"
    assert list(dest.rglob("*")) == [] or all(
        p.is_relative_to(dest) for p in dest.rglob("*")
    )


def test_symlink_escape_is_rejected(tmp_path):
    """A symlink member pointing outside the destination is not recreated."""
    from app.services.tar_utils import safe_extractall as _extract_safely

    archive = tmp_path / "symlink.tar"
    with tarfile.open(archive, "w") as tar:
        info = tarfile.TarInfo("escape")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        tar.addfile(info)

    dest = tmp_path / "dest"
    dest.mkdir()

    try:
        with tarfile.open(archive) as tar:
            _extract_safely(tar, str(dest))
    except Exception:
        pass

    link = dest / "escape"
    assert not link.is_symlink() or not str(link.resolve()).startswith("/etc"), (
        "an absolute symlink escaping the destination was recreated"
    )


def test_interrupted_job_is_recovered_on_startup(
    env, make_storage, make_job, localfs_config, db
):
    """A record left 'running' by a crash is failed and its containers restarted."""
    import app.main as main_module
    from app.models import BackupRecord

    job_name = f"interrupted-{env.run_id}"
    vol = env.create_volume("interrupted-vol", {"f.txt": "data"})
    container = env.create_workload(
        "interrupted-app", volumes={vol: "/data"}, labels={LABEL_KEY: job_name}
    )
    storage = make_storage(f"int-store-{env.run_id}", "localfs", localfs_config)
    job = make_job(job_name, storage, LABEL_KEY, job_name)

    # Simulate the state a crash mid-backup leaves behind: the container is
    # stopped and a record is stuck in "running" naming it.
    container.stop(timeout=10)
    assert env.container_status(container) != "running"

    from datetime import datetime, timezone

    stale = BackupRecord(
        job_id=job.id,
        status="running",
        started_at=datetime.now(timezone.utc),
        containers_stopped=json.dumps([container.name]),
    )
    db.add(stale)
    db.commit()
    stale_id = stale.id

    main_module._recover_interrupted_jobs()

    db.expire_all()
    recovered = db.get(BackupRecord, stale_id)
    assert recovered.status == "error", "interrupted record was not failed on startup"
    assert "restart" in (recovered.error_message or "").lower()
    assert env.container_status(container) == "running", (
        "container left stopped by an interrupted job was not restarted"
    )


def test_terminated_worker_still_restarts_containers(
    env, make_storage, make_job, localfs_config, db
):
    """A job whose worker process is killed does not leave containers stopped.

    Backup work runs in a separate process so a timeout can forcibly kill it.
    That kill also skips the worker's own cleanup, so the parent must restart
    the containers from what the record says were stopped.
    """
    from app.models import BackupRecord
    from app.services.backup_service import backup_service

    job_name = f"killed-{env.run_id}"
    vol = env.create_volume("killed-vol", {"f.txt": "data"})
    container = env.create_workload(
        "killed-app", volumes={vol: "/data"}, labels={LABEL_KEY: job_name}
    )
    storage = make_storage(f"killed-store-{env.run_id}", "localfs", localfs_config)
    job = make_job(job_name, storage, LABEL_KEY, job_name)

    # The state a terminated worker leaves behind: containers stopped, and a
    # record still marked running that names them.
    container.stop(timeout=10)
    assert env.container_status(container) != "running"

    from datetime import datetime, timezone

    record = BackupRecord(
        job_id=job.id,
        status="running",
        started_at=datetime.now(timezone.utc),
        containers_stopped=json.dumps([container.name]),
    )
    db.add(record)
    db.commit()
    record_id = record.id

    backup_service._mark_incomplete(job.id, "backup", "Job timed out after 1s")

    db.expire_all()
    updated = db.get(BackupRecord, record_id)
    assert updated.status == "error"
    assert env.container_status(container) == "running", (
        "containers were left stopped after the worker process was terminated"
    )


def test_imported_backup_without_a_volume_list_still_restores(
    env, make_storage, make_job, localfs_config, db
):
    """Records from archive discovery have no volume list and must still restore.

    POST /api/backups/import creates records with volumes_backed_up="[]" because
    it only sees a filename. The restore scoping must treat that as "no list to
    check against" rather than "no volumes are permitted".
    """
    from app.models import BackupRecord

    job_name = f"imported-{env.run_id}"
    original = {"data.txt": "from an imported archive"}
    vol = env.create_volume("imported-vol", original)
    env.create_workload(
        "imported-app", volumes={vol: "/data"}, labels={LABEL_KEY: job_name}
    )
    storage = make_storage(f"imp-store-{env.run_id}", "localfs", localfs_config)
    job = make_job(job_name, storage, LABEL_KEY, job_name)

    record = run_backup(job.id)
    assert record.status == "success", record.error_message

    # Re-create the record the way the import endpoint does: no volume list.
    imported = BackupRecord(
        job_id=job.id,
        status="success",
        size_bytes=record.size_bytes,
        storage_path=record.storage_path,
        started_at=record.started_at,
        completed_at=record.completed_at,
        containers_stopped="[]",
        volumes_backed_up="[]",
    )
    db.add(imported)
    db.commit()
    imported_id = imported.id

    env.client.containers.run(
        WORKLOAD_IMAGE,
        command=["sh", "-c", "rm -rf /data/* 2>/dev/null; true"],
        volumes={vol: {"bind": "/data", "mode": "rw"}},
        remove=True,
    )
    assert env.read_volume(vol) == {}

    run_restore(imported_id)

    assert env.read_volume(vol) == original, (
        "an imported backup record could not be restored"
    )
