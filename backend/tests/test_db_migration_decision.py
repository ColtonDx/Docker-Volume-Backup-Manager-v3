import app.database as db


def test_plaintext_always_migrates():
    assert db._decide_encrypted_action(True, "", False) == "plaintext_migrate"
    assert db._decide_encrypted_action(True, "", True) == "plaintext_migrate"


def test_new_scheme_ok():
    assert db._decide_encrypted_action(False, "new", False) == "ok"
    assert db._decide_encrypted_action(False, "new", True) == "ok"


def test_legacy_requires_optin():
    assert db._decide_encrypted_action(False, "legacy", False) == "refuse"
    assert db._decide_encrypted_action(False, "legacy", True) == "kdf_migrate"


def test_unknown_is_bad_key():
    assert db._decide_encrypted_action(False, "unknown", False) == "bad_key"
    assert db._decide_encrypted_action(False, "unknown", True) == "bad_key"


def test_pragma_escaping():
    assert db._escape_pragma("a'b") == "a''b"
    assert db._escape_pragma("plain") == "plain"


def test_wal_and_busy_timeout_enabled():
    from sqlalchemy import text

    with db.engine.connect() as conn:
        assert str(conn.execute(text("PRAGMA journal_mode")).scalar()).lower() == "wal"
        assert int(conn.execute(text("PRAGMA busy_timeout")).scalar()) == 5000
