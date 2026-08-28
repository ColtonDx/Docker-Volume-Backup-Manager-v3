"""Detection: container/volume discovery and container lifecycle handling.

Covers what the app finds and what it does to the user's containers, which is
the part with the most potential to be quietly wrong.
"""

from __future__ import annotations

import json

import pytest

from .test_backup_restore import LABEL_KEY, run_backup

pytestmark = pytest.mark.integration


def test_only_labelled_containers_are_selected(
    env, make_storage, make_job, localfs_config
):
    """A container without the job's label is not touched.

    The neighbour is deliberately left running: if discovery is too broad it
    would be stopped, and its volume would appear in the archive.
    """
    job_name = f"selective-{env.run_id}"

    target_vol = env.create_volume("sel-target", {"mine.txt": "target data"})
    other_vol = env.create_volume("sel-other", {"theirs.txt": "other data"})

    env.create_workload(
        "sel-target-app",
        volumes={target_vol: "/data"},
        labels={LABEL_KEY: job_name},
    )
    neighbour = env.create_workload(
        "sel-other-app",
        volumes={other_vol: "/data"},
        labels={LABEL_KEY: f"some-other-job-{env.run_id}"},
    )

    storage = make_storage(f"sel-store-{env.run_id}", "localfs", localfs_config)
    job = make_job(job_name, storage, LABEL_KEY, job_name)

    record = run_backup(job.id)

    assert record.status == "success", record.error_message
    assert json.loads(record.volumes_backed_up) == [target_vol]
    assert env.container_status(neighbour) == "running", (
        "a container belonging to a different job was stopped"
    )


def test_custom_label_key_is_honoured(env, make_storage, make_job, localfs_config):
    """Jobs can match on a label key other than the default dvbm.job."""
    custom_key = "com.example.backup"
    label_value = f"custom-{env.run_id}"

    vol = env.create_volume("custom-vol", {"f.txt": "custom"})
    env.create_workload(
        "custom-app",
        volumes={vol: "/data"},
        labels={custom_key: label_value},
    )

    storage = make_storage(f"custom-store-{env.run_id}", "localfs", localfs_config)
    job = make_job(f"customjob-{env.run_id}", storage, custom_key, label_value)

    record = run_backup(job.id)

    assert record.status == "success", record.error_message
    assert json.loads(record.volumes_backed_up) == [vol]


def test_stopped_containers_are_included_and_left_stopped(
    env, make_storage, make_job, localfs_config
):
    """A container that was already stopped is backed up but not started.

    Backing it up matters (its data is still real); starting it would be the app
    silently changing the user's container state.
    """
    job_name = f"stopped-{env.run_id}"

    vol = env.create_volume("stopped-vol", {"f.txt": "still here"})
    container = env.create_workload(
        "stopped-app",
        volumes={vol: "/data"},
        labels={LABEL_KEY: job_name},
        running=False,
    )

    storage = make_storage(f"stopped-store-{env.run_id}", "localfs", localfs_config)
    job = make_job(job_name, storage, LABEL_KEY, job_name)

    record = run_backup(job.id)

    assert record.status == "success", record.error_message
    assert json.loads(record.volumes_backed_up) == [vol]
    assert env.container_status(container) != "running", (
        "an already-stopped container was started by the backup"
    )


def test_running_containers_are_restarted_after_backup(
    env, make_storage, make_job, localfs_config
):
    """Containers stopped for the backup come back up."""
    job_name = f"restart-{env.run_id}"

    vol = env.create_volume("restart-vol", {"f.txt": "data"})
    container = env.create_workload(
        "restart-app",
        volumes={vol: "/data"},
        labels={LABEL_KEY: job_name},
    )
    assert env.container_status(container) == "running"

    storage = make_storage(f"restart-store-{env.run_id}", "localfs", localfs_config)
    job = make_job(job_name, storage, LABEL_KEY, job_name)

    record = run_backup(job.id)

    assert record.status == "success", record.error_message
    assert env.container_status(container) == "running", (
        "container was not restarted after a successful backup"
    )


def test_containers_are_restarted_when_upload_fails(
    env, make_storage, make_job, tmp_path
):
    """A failure after the stop step still brings the containers back.

    This is the regression test for the bug where the restart lived in the happy
    path only, so an upload failure left the user's containers down.
    """
    job_name = f"failrestart-{env.run_id}"

    vol = env.create_volume("failrestart-vol", {"f.txt": "data"})
    container = env.create_workload(
        "failrestart-app",
        volumes={vol: "/data"},
        labels={LABEL_KEY: job_name},
    )

    # A localfs path outside the allowed roots makes the upload raise.
    storage = make_storage(
        f"failrestart-store-{env.run_id}",
        "localfs",
        {"path": "/definitely/not/an/allowed/root"},
    )
    job = make_job(job_name, storage, LABEL_KEY, job_name)

    record = run_backup(job.id)

    assert record.status == "error", "upload to a forbidden path should fail the job"
    assert env.container_status(container) == "running", (
        "containers were left stopped after an upload failure"
    )


def test_no_matching_containers_fails_without_touching_anything(
    env, make_storage, make_job, localfs_config
):
    """A job whose label matches nothing fails cleanly."""
    storage = make_storage(f"nomatch-store-{env.run_id}", "localfs", localfs_config)
    job = make_job(
        f"nomatch-{env.run_id}", storage, LABEL_KEY, f"matches-nothing-{env.run_id}"
    )

    record = run_backup(job.id)

    assert record.status == "error"
    assert "no containers matched" in (record.error_message or "").lower()


def test_container_with_no_named_volumes_fails_clearly(
    env, make_storage, make_job, localfs_config
):
    """A labelled container with nothing to back up produces a clear error."""
    job_name = f"novol-{env.run_id}"

    env.create_workload(
        "novol-app",
        volumes={},
        labels={LABEL_KEY: job_name},
    )

    storage = make_storage(f"novol-store-{env.run_id}", "localfs", localfs_config)
    job = make_job(job_name, storage, LABEL_KEY, job_name)

    record = run_backup(job.id)

    assert record.status == "error"
    assert "no volumes" in (record.error_message or "").lower()


def test_temp_directory_is_clean_after_success_and_failure(
    env, make_storage, make_job, localfs_config, app_env
):
    """Staging files are removed on both paths.

    A failing job that leaks its archive fills the staging volume, after which
    every backup fails.
    """
    temp_dir = app_env["temp_dir"]

    vol = env.create_volume("tempclean-vol", {"f.txt": "data" * 1000})
    good_name = f"tempclean-ok-{env.run_id}"
    env.create_workload(
        "tempclean-app",
        volumes={vol: "/data"},
        labels={LABEL_KEY: good_name},
    )

    good_storage = make_storage(f"tc-good-{env.run_id}", "localfs", localfs_config)
    good_job = make_job(good_name, good_storage, LABEL_KEY, good_name)
    assert run_backup(good_job.id).status == "success"
    assert list(temp_dir.iterdir()) == [], "staging left behind after a success"

    bad_name = f"tempclean-bad-{env.run_id}"
    env.create_workload(
        "tempclean-bad-app",
        volumes={vol: "/data"},
        labels={LABEL_KEY: bad_name},
    )
    bad_storage = make_storage(
        f"tc-bad-{env.run_id}", "localfs", {"path": "/not/allowed"}
    )
    bad_job = make_job(bad_name, bad_storage, LABEL_KEY, bad_name)
    assert run_backup(bad_job.id).status == "error"
    assert list(temp_dir.iterdir()) == [], "staging left behind after a failure"
