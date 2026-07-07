import hashlib
import logging
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool

from app.config import settings

log = logging.getLogger(__name__)

Base = declarative_base()


# ---------------------------------------------------------------------------
# SQLCipher helpers
# ---------------------------------------------------------------------------

SQLITE_MAGIC = b"SQLite format 3\x00"

# SQLCipher format the app writes. Pinning cipher_compatibility makes the
# on-disk format independent of the linked SQLCipher library's default
# (v3 vs v4), restoring version-portability while still using SQLCipher's
# audited KDF (PBKDF2) for key stretching.
_CIPHER_COMPATIBILITY = 4


def _hex_key(passphrase: str) -> str:
    """
    Derive a 32-byte (256-bit) hex key from a passphrase via a single SHA-256.

    LEGACY ONLY. This is the old key-derivation scheme (raw x'hex' key, which
    bypasses SQLCipher's KDF). A single unsalted hash offers no key stretching,
    so it is retained solely to open/migrate databases created by older
    versions — new databases use the native SQLCipher KDF (see _apply_new_key).
    """
    return hashlib.sha256(passphrase.encode()).hexdigest()


def _escape_pragma(value: str) -> str:
    """Escape a value for safe inclusion in a single-quoted PRAGMA statement."""
    return value.replace("'", "''")


def _apply_new_key(conn, passphrase: str) -> None:
    """Unlock a connection with the native-KDF scheme (key then pinned compat)."""
    conn.execute(f"PRAGMA key = '{_escape_pragma(passphrase)}'")
    conn.execute(f"PRAGMA cipher_compatibility = {_CIPHER_COMPATIBILITY}")


def _apply_legacy_key(conn, passphrase: str) -> None:
    """Unlock a connection with the legacy raw-hex-key scheme."""
    conn.execute(f"PRAGMA key = \"x'{_hex_key(passphrase)}'\"")


def _opens_with(db_path: Path, passphrase: str, apply_key) -> bool:
    """Return True if the DB file can be unlocked+read using apply_key."""
    import sqlcipher3

    conn = sqlcipher3.connect(str(db_path))
    try:
        apply_key(conn, passphrase)
        conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
        return True
    except Exception:
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _detect_encrypted_scheme(db_path: Path, passphrase: str) -> str:
    """Classify an encrypted DB file: 'new', 'legacy', or 'unknown' (bad key)."""
    if _opens_with(db_path, passphrase, _apply_new_key):
        return "new"
    if _opens_with(db_path, passphrase, _apply_legacy_key):
        return "legacy"
    return "unknown"


def _decide_encrypted_action(is_plaintext: bool, scheme: str, migrate_flag: bool) -> str:
    """Pure decision helper (unit-testable) for how to handle an existing DB file.

    Returns one of: 'plaintext_migrate', 'ok', 'kdf_migrate', 'refuse', 'bad_key'.
    """
    if is_plaintext:
        return "plaintext_migrate"
    if scheme == "new":
        return "ok"
    if scheme == "legacy":
        return "kdf_migrate" if migrate_flag else "refuse"
    return "bad_key"


def _sqlcipher_creator(db_path: str, passphrase: str):
    """Return a DBAPI connection factory for use with SQLAlchemy's creator= arg."""
    import sqlcipher3

    def creator():
        conn = sqlcipher3.connect(db_path)
        _apply_new_key(conn, passphrase)
        return conn

    return creator


def _write_encrypted_from_dump(sql_statements, dest_path: Path, passphrase: str) -> None:
    """Create a new native-KDF encrypted DB at dest_path from SQL dump statements
    and verify it opens and is readable. Raises on any failure."""
    import sqlcipher3

    enc_conn = sqlcipher3.connect(str(dest_path))
    try:
        _apply_new_key(enc_conn, passphrase)
        for stmt in sql_statements:
            enc_conn.execute(stmt)
        enc_conn.commit()
    finally:
        enc_conn.close()

    if not _opens_with(dest_path, passphrase, _apply_new_key):
        raise RuntimeError(f"Verification failed: {dest_path} did not open with the new KDF")


def _migrate_plaintext_to_encrypted(db_path: Path, passphrase: str) -> None:
    """
    One-time migration: encrypt an existing plaintext SQLite database in place,
    using the native SQLCipher KDF scheme.

    Steps:
      1. Verify the file has the SQLite3 magic header (not already encrypted).
      2. Dump all SQL from the plain DB via sqlite3.iterdump().
      3. Write the dump into a new SQLCipher-encrypted DB at a temp path.
      4. Verify the new encrypted DB opens and is readable.
      5. Atomically replace the original file with the encrypted one.
      6. Keep the plaintext backup at <name>.plaintext.bak.
    """
    with open(db_path, "rb") as fh:
        header = fh.read(16)

    if header != SQLITE_MAGIC:
        # Already encrypted (or corrupt) — do not attempt migration.
        return

    backup_path = db_path.with_suffix(".plaintext.bak")
    log.warning(
        "DB_ENCRYPTION_KEY is set but %s is a plaintext SQLite3 database. "
        "Migrating to SQLCipher encryption. Backup retained at: %s",
        db_path,
        backup_path,
    )

    # Step 1: read full SQL dump from the plaintext DB
    plain_conn = sqlite3.connect(str(db_path))
    try:
        sql_statements = list(plain_conn.iterdump())
    finally:
        plain_conn.close()

    # Step 2: back up the original
    shutil.copy2(str(db_path), str(backup_path))

    tmp_path = db_path.with_suffix(".encrypting_tmp")
    if tmp_path.exists():
        tmp_path.unlink()

    try:
        # Steps 3 & 4: write + verify encrypted DB
        _write_encrypted_from_dump(sql_statements, tmp_path, passphrase)
        # Step 5: atomic replace (POSIX guarantee: same filesystem)
        tmp_path.replace(db_path)
        log.info("Encryption migration complete. Plaintext backup: %s", backup_path)

    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def _migrate_legacy_kdf_to_new(db_path: Path, passphrase: str) -> None:
    """
    Re-encrypt a legacy (raw-hex-key) database with the native SQLCipher KDF.

    Uses a dump-and-reload (not in-place PRAGMA rekey) so the original file is
    never mutated until a fully-verified replacement exists:
      1. Dump all SQL from the legacy-scheme DB.
      2. Write + verify a new-scheme encrypted DB at a temp path.
      3. Back up the original to <name>.prekdf.bak.
      4. Atomically replace the original with the new-scheme DB.
    On any failure the original file is left untouched.
    """
    import sqlcipher3

    log.warning(
        "MIGRATE_ENCRYPTED_DB=true: migrating legacy-encrypted database %s to the "
        "native SQLCipher KDF. A backup will be kept at %s. Ensure you have your "
        "own backup before proceeding.",
        db_path,
        db_path.with_suffix(".prekdf.bak"),
    )

    # Step 1: dump from the legacy-scheme DB
    src = sqlcipher3.connect(str(db_path))
    try:
        _apply_legacy_key(src, passphrase)
        src.execute("SELECT count(*) FROM sqlite_master").fetchone()  # confirm unlock
        sql_statements = list(src.iterdump())
    finally:
        src.close()

    tmp_path = db_path.with_suffix(".rekey_tmp")
    if tmp_path.exists():
        tmp_path.unlink()

    try:
        # Steps 2: write + verify the new-scheme DB
        _write_encrypted_from_dump(sql_statements, tmp_path, passphrase)

        # Step 3: back up the original, then Step 4: atomic replace
        backup_path = db_path.with_suffix(".prekdf.bak")
        shutil.copy2(str(db_path), str(backup_path))
        tmp_path.replace(db_path)
        log.info("Encryption KDF migration complete. Pre-migration backup: %s", backup_path)

    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


# ---------------------------------------------------------------------------
# Pre-engine file migrations (filename renames, etc.)
# These run before the engine is created and cannot be tracked in the DB.
# ---------------------------------------------------------------------------

def _pre_engine_migrations() -> None:
    """Handle filesystem-level changes that must occur before the engine connects."""
    # v2 → v3: database was renamed from backup_buddy.db to dvbm.db
    if not settings.DB_PATH:
        old = settings.DATA_DIR / "backup_buddy.db"
        new = settings.DATA_DIR / "dvbm.db"
        if old.exists() and not new.exists():
            old.rename(new)
            log.info("Renamed database file: backup_buddy.db → dvbm.db")


# ---------------------------------------------------------------------------
# Engine construction
# ---------------------------------------------------------------------------

def _build_engine():
    _pre_engine_migrations()

    passphrase = settings.DB_ENCRYPTION_KEY

    if not passphrase:
        # Plain SQLite — no encryption.
        return create_engine(
            settings.database_url,
            connect_args={"check_same_thread": False},
            echo=False,
        )

    # Ensure sqlcipher3 is available before proceeding
    try:
        import sqlcipher3  # noqa: F401
    except ImportError:
        log.error(
            "DB_ENCRYPTION_KEY is set but sqlcipher3 is not importable. "
            "Ensure the container was built with libsqlcipher-dev installed."
        )
        raise

    db_path = settings.db_file_path
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Decide how to handle an existing DB file (plaintext vs already-encrypted
    # with the new or legacy scheme) before opening it.
    if db_path.exists():
        with open(db_path, "rb") as fh:
            is_plaintext = fh.read(16) == SQLITE_MAGIC

        scheme = "" if is_plaintext else _detect_encrypted_scheme(db_path, passphrase)
        action = _decide_encrypted_action(is_plaintext, scheme, settings.MIGRATE_ENCRYPTED_DB)

        if action == "plaintext_migrate":
            _migrate_plaintext_to_encrypted(db_path, passphrase)
        elif action == "kdf_migrate":
            _migrate_legacy_kdf_to_new(db_path, passphrase)
        elif action == "refuse":
            raise RuntimeError(
                f"The database at {db_path} is encrypted with the legacy "
                "(unsalted SHA-256) key-derivation scheme, which is being "
                "upgraded to SQLCipher's native KDF. Back up your data volume, "
                "then set MIGRATE_ENCRYPTED_DB=true to perform a one-time in-place "
                "re-encryption (a verified .prekdf.bak backup is kept). Refusing "
                "to start so you can roll back if needed."
            )
        elif action == "bad_key":
            raise RuntimeError(
                f"The database at {db_path} could not be unlocked with the "
                "provided DB_ENCRYPTION_KEY (neither the new nor the legacy "
                "scheme). Check that DB_ENCRYPTION_KEY matches the key the "
                "database was created with."
            )
        # action == "ok": already new-scheme, nothing to do.

    creator = _sqlcipher_creator(str(db_path), passphrase)

    # NullPool: every session checkout creates a fresh DBAPI connection so that
    # PRAGMA key is always the first statement issued — SQLCipher requires this.
    return create_engine(
        "sqlite://",   # URL is a dialect hint only; creator= handles the actual connect
        creator=creator,
        poolclass=NullPool,
        echo=False,
    )


engine = _build_engine()


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, connection_record) -> None:
    """Enable WAL and a busy timeout on every connection.

    WAL lets readers and a writer proceed concurrently, and busy_timeout makes a
    connection wait for a lock instead of failing immediately with
    "database is locked" — the background backup workers write while the API
    reads. Runs after the (encrypted) creator's key PRAGMAs.
    """
    try:
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()
    except Exception:
        log.debug("Could not set SQLite pragmas", exc_info=True)


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI dependency that provides a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Versioned schema migrations
# ---------------------------------------------------------------------------
# Rules for adding a new migration:
#   1. Write a function _mNNN_description(conn) that makes the change.
#   2. Append (NNN, "short description", _mNNN_description) to MIGRATIONS.
#   3. Never edit or remove existing entries — only append.
#   4. Migrations must be idempotent (safe to call even if partially applied).
# ---------------------------------------------------------------------------

def _m001_add_label_columns(conn) -> None:
    """Add label_key and label_value columns to backup_jobs."""
    result = conn.execute(text("PRAGMA table_info(backup_jobs)"))
    existing = {row[1] for row in result}
    if "label_key" not in existing:
        conn.execute(text(
            "ALTER TABLE backup_jobs ADD COLUMN label_key VARCHAR NOT NULL DEFAULT 'dvbm.job'"
        ))
    if "label_value" not in existing:
        conn.execute(text(
            "ALTER TABLE backup_jobs ADD COLUMN label_value VARCHAR NOT NULL DEFAULT ''"
        ))
    conn.commit()


def _m003_add_job_timeout(conn) -> None:
    """Add per-job timeout_seconds column to backup_jobs."""
    result = conn.execute(text("PRAGMA table_info(backup_jobs)"))
    existing = {row[1] for row in result}
    if "timeout_seconds" not in existing:
        conn.execute(text("ALTER TABLE backup_jobs ADD COLUMN timeout_seconds INTEGER"))
    conn.commit()


def _m002_add_indexes(conn) -> None:
    """Add indexes on the most-queried columns of backup_records and log_entries."""
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_backup_records_job_id ON backup_records (job_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_backup_records_started_at ON backup_records (started_at)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_log_entries_created_at ON log_entries (created_at)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_log_entries_job_name ON log_entries (job_name)"))
    conn.commit()


def _m004_normalize_timezone(conn) -> None:
    """Normalize the stored timezone setting to a valid IANA key.

    Older versions shipped with the default timezone set to "utc" (lowercase),
    which zoneinfo (used by APScheduler 3.11+) rejects. This migration corrects
    any stored value that zoneinfo cannot load.
    """
    import json as _json
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    row = conn.execute(text("SELECT value FROM settings WHERE key = 'timezone'")).fetchone()
    if not row:
        return

    try:
        tz = _json.loads(row[0])
    except Exception:
        tz = row[0]

    if not isinstance(tz, str) or not tz.strip():
        return

    tz = tz.strip()

    # Already valid — nothing to do.
    try:
        ZoneInfo(tz)
        return
    except (ZoneInfoNotFoundError, KeyError):
        pass

    # Try uppercase — fixes "utc" -> "UTC" and similar.
    normalized = tz.upper()
    try:
        ZoneInfo(normalized)
    except (ZoneInfoNotFoundError, KeyError):
        # Cannot determine the correct timezone; fall back to UTC.
        normalized = "UTC"

    conn.execute(
        text("UPDATE settings SET value = :v WHERE key = 'timezone'"),
        {"v": _json.dumps(normalized)},
    )
    conn.commit()
    log.info("Migration 4: normalized stored timezone %r -> %r", tz, normalized)


# Registry: (version, description, function)
# APPEND ONLY — never edit or remove existing rows.
MIGRATIONS: list[tuple[int, str, object]] = [
    (1, "add label_key and label_value to backup_jobs", _m001_add_label_columns),
    (2, "add indexes on backup_records and log_entries", _m002_add_indexes),
    (3, "add timeout_seconds to backup_jobs", _m003_add_job_timeout),
    (4, "normalize stored timezone to valid IANA key", _m004_normalize_timezone),
]


def _ensure_migrations_table(conn) -> None:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version     INTEGER PRIMARY KEY,
            description TEXT    NOT NULL,
            applied_at  TEXT    NOT NULL
        )
    """))
    conn.commit()


def _applied_versions(conn) -> set[int]:
    result = conn.execute(text("SELECT version FROM schema_migrations"))
    return {row[0] for row in result}


def _mark_applied(conn, version: int, description: str) -> None:
    conn.execute(
        text("INSERT INTO schema_migrations (version, description, applied_at) VALUES (:v, :d, :t)"),
        {"v": version, "d": description, "t": datetime.now(timezone.utc).isoformat()},
    )
    conn.commit()


def _run_migrations(eng) -> None:
    with eng.connect() as conn:
        _ensure_migrations_table(conn)
        applied = _applied_versions(conn)
        for version, description, fn in MIGRATIONS:
            if version not in applied:
                log.info("Applying schema migration %d: %s", version, description)
                fn(conn)  # type: ignore[operator]
                _mark_applied(conn, version, description)
                log.info("Schema migration %d applied", version)


# ---------------------------------------------------------------------------
# Public init
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create all tables (fresh install) and apply any pending migrations."""
    from app import models  # noqa: F401 – ensure models are registered on Base

    Base.metadata.create_all(bind=engine)
    _run_migrations(engine)
