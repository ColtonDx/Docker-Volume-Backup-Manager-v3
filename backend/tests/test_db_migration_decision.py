import app.database as db


def test_plaintext_always_migrates():
    assert db._decide_encrypted_action(True, "") == "plaintext_migrate"


def test_new_scheme_ok():
    assert db._decide_encrypted_action(False, "new") == "ok"


def test_legacy_migrates_automatically():
    assert db._decide_encrypted_action(False, "legacy") == "kdf_migrate"


def test_unknown_is_bad_key():
    assert db._decide_encrypted_action(False, "unknown") == "bad_key"


def test_pragma_escaping():
    assert db._escape_pragma("a'b") == "a''b"
    assert db._escape_pragma("plain") == "plain"


def test_iterdump_statements_uses_native_iterdump(tmp_path):
    import sqlite3

    p = tmp_path / "s.db"
    conn = sqlite3.connect(p)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.executemany("INSERT INTO t (v) VALUES (?)", [("a'b",), ("b",), (None,)])
    conn.commit()
    stmts = db._iterdump_statements(conn)
    conn.close()
    assert any("CREATE TABLE" in s for s in stmts)
    assert any("INSERT INTO" in s for s in stmts)


def test_iterdump_statements_fallback_without_iterdump(tmp_path):
    """sqlcipher3 connections lack iterdump(); the fallback must still work and
    round-trip schema + data."""
    import sqlite3

    p = tmp_path / "s.db"
    conn = sqlite3.connect(p)
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.execute("CREATE INDEX ix_t_v ON t(v)")
    conn.executemany("INSERT INTO t (v) VALUES (?)", [("a'b",), ("b",), (None,)])
    conn.commit()
    conn.close()

    class NoIterdump:
        def __init__(self, c):
            self._c = c

        def cursor(self):
            return self._c.cursor()

        def execute(self, *a, **k):
            return self._c.execute(*a, **k)

        def __getattr__(self, name):
            if name == "iterdump":
                raise AttributeError("iterdump")
            return getattr(self._c, name)

    src = sqlite3.connect(p)
    stmts = db._iterdump_statements(NoIterdump(src))
    src.close()

    # replay into a fresh db and confirm data + index survive
    p2 = tmp_path / "s2.db"
    dst = sqlite3.connect(p2)
    for s in stmts:
        dst.execute(s)
    dst.commit()
    rows = dst.execute("SELECT v FROM t ORDER BY id").fetchall()
    idx = dst.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name='ix_t_v'"
    ).fetchone()
    dst.close()
    assert rows == [("a'b",), ("b",), (None,)]
    assert idx is not None


def test_wal_and_busy_timeout_enabled():
    from sqlalchemy import text

    with db.engine.connect() as conn:
        assert str(conn.execute(text("PRAGMA journal_mode")).scalar()).lower() == "wal"
        assert int(conn.execute(text("PRAGMA busy_timeout")).scalar()) == 5000
