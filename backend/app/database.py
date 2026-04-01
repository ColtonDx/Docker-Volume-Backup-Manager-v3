import hashlib
import logging
import shutil
import sqlite3
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
# Engine construction
# ---------------------------------------------------------------------------

def _build_engine():
    passphrase = settings.DB_ENCRYPTION_KEY

    if not passphrase:
        # Original behaviour — plain SQLite, no changes.
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


def init_db():
    """Create all tables and run lightweight migrations for new columns."""
    from app import models  # noqa: F401 – ensure models are imported

    Base.metadata.create_all(bind=engine)
    _migrate(engine)


def _migrate(eng):
    """Add columns that may be missing from older schemas (SQLite-safe)."""
    migrations = [
        ("backup_jobs", "label_key", "VARCHAR DEFAULT 'backup-buddy.job' NOT NULL"),
        ("backup_jobs", "label_value", "VARCHAR DEFAULT '' NOT NULL"),
    ]

    with eng.connect() as conn:
        for table, column, col_def in migrations:
            result = conn.execute(text(f"PRAGMA table_info({table})"))
            existing_cols = {row[1] for row in result}
            if column not in existing_cols:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}"))
                conn.commit()
                log.info("Migration: added %s.%s", table, column)
