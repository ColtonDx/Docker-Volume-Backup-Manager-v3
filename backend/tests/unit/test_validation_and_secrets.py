"""Fast checks for pure logic: no Docker, no network, no database.

These cover the input validation and secret-handling rules, which are cheap to
test directly and easy to regress silently.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


# ----------------------------------------------------------------------
# Schema validation
# ----------------------------------------------------------------------

def test_min_backups_below_one_is_rejected():
    """A policy must never be able to delete a job's last backup."""
    from pydantic import ValidationError

    from app.schemas import RetentionPolicyCreate

    with pytest.raises(ValidationError):
        RetentionPolicyCreate(name="p", retention_days=7, min_backups=0)

    assert RetentionPolicyCreate(
        name="p", retention_days=7, min_backups=1
    ).min_backups == 1


def test_max_backups_below_min_is_rejected():
    from pydantic import ValidationError

    from app.schemas import RetentionPolicyCreate

    with pytest.raises(ValidationError):
        RetentionPolicyCreate(
            name="p", retention_days=7, min_backups=5, max_backups=3
        )


@pytest.mark.parametrize(
    "expression",
    ["not a cron", "0 2 * *", "99 2 * * *", "", "* * * * * *"],
)
def test_invalid_cron_is_rejected(expression):
    """An unparseable schedule must fail on save, not silently never fire."""
    from pydantic import ValidationError

    from app.schemas import ScheduleCreate

    with pytest.raises(ValidationError):
        ScheduleCreate(name="s", cron=expression)


@pytest.mark.parametrize(
    "expression",
    ["0 2 * * *", "*/15 * * * *", "0 0 1 * *", "30 3 * * 0"],
)
def test_valid_cron_is_accepted(expression):
    from app.schemas import ScheduleCreate

    assert ScheduleCreate(name="s", cron=expression).cron == expression


@pytest.mark.parametrize(
    "name",
    ["../etc/passwd", "job/../../x", "job/sub", "job\x00null", "job;rm -rf"],
)
def test_unsafe_job_names_are_rejected(name):
    """Job names become archive filenames, so they must stay path-safe."""
    from pydantic import ValidationError

    from app.schemas import BackupJobCreate

    with pytest.raises(ValidationError):
        BackupJobCreate(name=name, storage_id=1)


@pytest.mark.parametrize("name", ["my-app", "my_app", "My App 2", "app.v1"])
def test_reasonable_job_names_are_accepted(name):
    from app.schemas import BackupJobCreate

    assert BackupJobCreate(name=name, storage_id=1).name == name.strip()


# ----------------------------------------------------------------------
# Secret redaction
# ----------------------------------------------------------------------

def test_secrets_are_redacted_in_output():
    from app.secrets_mask import SENTINEL, mask_config

    redacted = mask_config({
        "bucket": "my-bucket",
        "access_key_id": "AKIAEXAMPLE",
        "secret_access_key": "supersecret",
        "password": "hunter2",
        "region": "us-east-1",
    })

    assert redacted["bucket"] == "my-bucket"
    assert redacted["region"] == "us-east-1"
    assert redacted["secret_access_key"] == SENTINEL
    assert redacted["password"] == SENTINEL
    assert "supersecret" not in json.dumps(redacted)
    assert "hunter2" not in json.dumps(redacted)


def test_redacted_values_do_not_overwrite_stored_secrets():
    """A read-modify-write cycle must not destroy credentials."""
    from app.secrets_mask import SENTINEL, unmask_config

    stored = {"password": "real-secret", "host": "old-host"}
    incoming = {"password": SENTINEL, "host": "new-host"}

    merged = unmask_config(incoming, stored)

    assert merged["password"] == "real-secret"
    assert merged["host"] == "new-host"


def test_placeholder_with_no_stored_value_is_dropped():
    """The literal placeholder must never be saved as if it were a credential."""
    from app.secrets_mask import SENTINEL, unmask_config

    merged = unmask_config({"password": SENTINEL, "host": "h"}, {})

    assert "password" not in merged
    assert merged["host"] == "h"


def test_new_secret_value_replaces_the_stored_one():
    from app.secrets_mask import unmask_config

    merged = unmask_config({"password": "new"}, {"password": "old"})

    assert merged["password"] == "new"


def test_masking_leaves_non_secret_fields_alone():
    """Only credential fields are masked; the rest of the config is readable."""
    from app.secrets_mask import SENTINEL, mask_config

    out = mask_config({"bucket": "b", "region": "us-east-1", "secret_access_key": "leak-me"})

    assert out["bucket"] == "b"
    assert out["region"] == "us-east-1"
    assert out["secret_access_key"] == SENTINEL


def test_empty_secret_is_not_masked():
    """An unset credential stays empty rather than becoming a sentinel to save."""
    from app.secrets_mask import mask_config

    assert mask_config({"password": ""})["password"] == ""


# ----------------------------------------------------------------------
# rclone flag allowlist
# ----------------------------------------------------------------------

@pytest.mark.parametrize(
    "flags",
    [
        "--config /data/dvbm.db",
        "--log-file /app/static/leak.txt",
        "--dump bodies",
        "--rc-addr :5572",
        "; rm -rf /",
    ],
)
def test_dangerous_rclone_flags_are_rejected(flags):
    from app.services.storage_service import StorageService

    with pytest.raises(ValueError):
        StorageService._rclone_extra_flags({"flags": flags})


@pytest.mark.parametrize(
    "flags",
    ["--transfers=4", "--bwlimit=10M", "--checkers=8 --retries=3", "--timeout=5m", ""],
)
def test_tuning_rclone_flags_are_accepted(flags):
    from app.services.storage_service import StorageService

    assert StorageService._rclone_extra_flags({"flags": flags}) == flags.split()


# ----------------------------------------------------------------------
# Local filesystem confinement
# ----------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/etc", "/", "/var/run", "/etc/../etc"])
def test_localfs_paths_outside_allowed_roots_are_rejected(path):
    from app.services.storage_service import StorageService

    with pytest.raises(ValueError):
        StorageService._localfs_resolve(path)


# ----------------------------------------------------------------------
# SSRF guard
# ----------------------------------------------------------------------

@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",   # cloud metadata
        "http://127.0.0.1:8000/",                     # loopback (app's own container)
        "file:///etc/passwd",                         # non-HTTP scheme
        "gopher://example.com/",
    ],
)
def test_internal_and_non_http_notification_urls_are_blocked(url):
    from app.services.notification_service import _validate_outbound_url

    with pytest.raises(Exception):
        _validate_outbound_url(url)


@pytest.mark.parametrize("url", ["http://192.168.1.50:8080/hook", "https://10.0.0.5"])
def test_lan_notification_targets_are_allowed_by_default(url):
    """A self-hosted Gotify/ntfy on the LAN is the common homelab case.

    Set BLOCK_PRIVATE_NOTIFICATION_URLS=true to refuse these instead.
    """
    from app.services.notification_service import _validate_outbound_url

    _validate_outbound_url(url)  # must not raise


# ----------------------------------------------------------------------
# Password comparison
# ----------------------------------------------------------------------

def test_password_check_rejects_wrong_values():
    from app.auth import verify_password
    from app.config import settings

    previous = settings.AUTH_PASSWORD
    settings.AUTH_PASSWORD = "correct-horse"
    try:
        assert verify_password("correct-horse") is True
        assert verify_password("wrong") is False
        assert verify_password("") is False
        assert verify_password("correct-hors") is False
    finally:
        settings.AUTH_PASSWORD = previous


def test_login_throttle_delay_grows_with_failures():
    """Repeated failures progressively slow further attempts."""
    from app.auth import LoginThrottle

    throttle = LoginThrottle()
    assert throttle.current_delay() == 0.0

    throttle.record_failure()
    first = throttle.current_delay()
    assert first > 0, "no delay applied after a failed login"

    throttle.record_failure()
    assert throttle.current_delay() > first, "delay did not increase with failures"


def test_login_throttle_delay_is_capped():
    """The delay never grows without bound, so the operator is not locked out."""
    from app.auth import LoginThrottle

    throttle = LoginThrottle()
    for _ in range(50):
        throttle.record_failure()
    assert throttle.current_delay() == LoginThrottle.MAX_DELAY


def test_successful_login_clears_the_failure_count():
    from app.auth import LoginThrottle

    throttle = LoginThrottle()
    throttle.record_failure()
    throttle.record_failure()
    throttle.record_success()
    assert throttle.current_delay() == 0.0, (
        "failure count was not reset by a successful login"
    )
