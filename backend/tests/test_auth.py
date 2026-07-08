"""Auth tests. Require python-jose (installed from requirements)."""

from types import SimpleNamespace

import pytest

from app.auth import (
    LoginThrottle,
    create_access_token,
    get_current_user,
    token_version_store,
    verify_password,
)


def _creds(token: str) -> SimpleNamespace:
    return SimpleNamespace(credentials=token)


def test_verify_password_constant_time_correct():
    assert verify_password("test-password-123") is True
    assert verify_password("wrong") is False
    assert verify_password("test-password-1234") is False
    # non-ascii input must not raise
    assert verify_password("päß") is False


def test_login_throttle_progression_and_reset():
    t = LoginThrottle()
    assert t.current_delay() == 0.0
    t.record_failure()
    assert t.current_delay() == 0.5
    t.record_failure()
    assert t.current_delay() == 1.0
    t.record_failure()
    assert t.current_delay() == 2.0
    for _ in range(10):
        t.record_failure()
    assert t.current_delay() == LoginThrottle.MAX_DELAY
    t.record_success()
    assert t.current_delay() == 0.0


def test_token_roundtrip_and_revocation():
    token = create_access_token()
    assert get_current_user(_creds(token)) == "admin"

    # bumping the version revokes previously-issued tokens
    token_version_store.bump()
    with pytest.raises(Exception):
        get_current_user(_creds(token))

    # a freshly-issued token carries the new version and is accepted
    assert get_current_user(_creds(create_access_token())) == "admin"


def test_token_without_version_claim_rejected():
    from app.config import settings
    from jose import jwt

    payload = {"sub": "admin"}  # no "tv" claim (pre-upgrade token)
    stale = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    with pytest.raises(Exception):
        get_current_user(_creds(stale))


def test_missing_credentials_rejected():
    with pytest.raises(Exception):
        get_current_user(None)
