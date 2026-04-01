import hashlib
import logging
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from sqlalchemy.pool import NullPool

from app.config import settings

log = logging.getLogger(__name__)

Base = declarative_base()


# ---------------------------------------------------------------------------
# SQLCipher helpers
# ---------------------------------------------------------------------------

def _hex_key(passphrase: str) -> str:
    """
    Derive a 32-byte (256-bit) hex key from an arbitrary passphrase via SHA-256.

    Using the x'hex' PRAGMA form bypasses SQLCipher's KDF entirely, giving a
    deterministic key that is independent of SQLCipher version defaults (v3 vs v4
    changed KDF iterations and cipher settings).  This makes the database portable
    across SQLCipher versions as long as the same passphrase is supplied.
    """
    return hashlib.sha256(passphrase.encode()).hexdigest()


def _sqlcipher_creator(db_path: str, hex_key_val: str):
    """Return a DBAPI connection factory for use with SQLAlchemy's creator= arg."""
    import sqlcipher3

    def creator():
        conn = sqlcipher3.connect(db_path)
        conn.execute(f"PRAGMA key = \"x'{hex_key_val}'\"")
        return conn

    return creator


def _migrate_plaintext_to_encrypted(db_path: Path, passphrase: str) -> None:
    """
    One-time migration: encrypt an existing plaintext SQLite database in place.

    Steps:
      1. Verify the file has the SQLite3 magic header (not already encrypted).
      2. Dump all SQL from the plain DB via sqlite3.iterdump().
      3. Write the dump into a new SQLCipher-encrypted DB at a temp path.
      4. Verify the new encrypted DB opens and is readable.
      5. Atomically replace the original file with the encrypted one.
      6. Keep the plaintext backup at <name>.plaintext.bak.
    """
    import sqlcipher3

    SQLITE_MAGIC = b"SQLite format 3\x00"
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
    hk = _hex_key(passphrase)

    try:
        # Step 3: write encrypted DB
        enc_conn = sqlcipher3.connect(str(tmp_path))
        try:
            enc_conn.execute(f"PRAGMA key = \"x'{hk}'\"")
            for stmt in sql_statements:
                enc_conn.execute(stmt)
            enc_conn.commit()
        finally:
            enc_conn.close()

        # Step 4: verify
        verify_conn = sqlcipher3.connect(str(tmp_path))
        try:
            verify_conn.execute(f"PRAGMA key = \"x'{hk}'\"")
            verify_conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
        finally:
            verify_conn.close()

        # Step 5: atomic replace (POSIX guarantee: same filesystem)
        tmp_path.replace(db_path)
        log.info("Encryption migration complete. Plaintext backup: %s", backup_path)

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

    # Migrate from plaintext if the DB file already exists
    if db_path.exists():
        _migrate_plaintext_to_encrypted(db_path, passphrase)

    hk = _hex_key(passphrase)
    creator = _sqlcipher_creator(str(db_path), hk)

    # NullPool: every session checkout creates a fresh DBAPI connection so that
    # PRAGMA key is always the first statement issued — SQLCipher requires this.
    return create_engine(
        "sqlite://",   # URL is a dialect hint only; creator= handles the actual connect
        creator=creator,
        poolclass=NullPool,
        echo=False,
    )


engine = _build_engine()

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


def _m002_add_indexes(conn) -> None:
    """Add indexes on the most-queried columns of backup_records and log_entries."""
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_backup_records_job_id ON backup_records (job_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_backup_records_started_at ON backup_records (started_at)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_log_entries_created_at ON log_entries (created_at)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_log_entries_job_name ON log_entries (job_name)"))
    conn.commit()


# Registry: (version, description, function)
# APPEND ONLY — never edit or remove existing rows.
MIGRATIONS: list[tuple[int, str, object]] = [
    (1, "add label_key and label_value to backup_jobs", _m001_add_label_columns),
    (2, "add indexes on backup_records and log_entries", _m002_add_indexes),
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
