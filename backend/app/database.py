from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session

from app.config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


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
    import logging
    log = logging.getLogger(__name__)

    migrations = [
        ("backup_jobs", "label_key", "VARCHAR DEFAULT 'backup-buddy.job' NOT NULL"),
        ("backup_jobs", "label_value", "VARCHAR DEFAULT '' NOT NULL"),
        ("backup_jobs", "uptime_kuma_monitor_id", "INTEGER"),
    ]

    with eng.connect() as conn:
        for table, column, col_def in migrations:
            # Check if column already exists
            result = conn.execute(
                __import__("sqlalchemy").text(f"PRAGMA table_info({table})")
            )
            existing_cols = {row[1] for row in result}
            if column not in existing_cols:
                conn.execute(
                    __import__("sqlalchemy").text(
                        f"ALTER TABLE {table} ADD COLUMN {column} {col_def}"
                    )
                )
                conn.commit()
                log.info("Migration: added %s.%s", table, column)
