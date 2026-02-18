from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    BigInteger,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Storage Backends
# ---------------------------------------------------------------------------
class StorageBackend(Base):
    __tablename__ = "storage_backends"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)  # localfs | s3 | ftp | rclone
    # Type-specific config stored as JSON-encoded text
    config_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


# ---------------------------------------------------------------------------
# Schedules
# ---------------------------------------------------------------------------
class Schedule(Base):
    __tablename__ = "schedules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    cron = Column(String, nullable=False)
    description = Column(String, nullable=True)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


# ---------------------------------------------------------------------------
# Retention Policies
# ---------------------------------------------------------------------------
class RetentionPolicy(Base):
    __tablename__ = "retention_policies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    retention_days = Column(Integer, nullable=False)
    min_backups = Column(Integer, default=1)
    max_backups = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


# ---------------------------------------------------------------------------
# Backup Jobs
# ---------------------------------------------------------------------------
class BackupJob(Base):
    __tablename__ = "backup_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    storage_id = Column(Integer, ForeignKey("storage_backends.id"), nullable=False)
    schedule_id = Column(Integer, ForeignKey("schedules.id", ondelete="SET NULL"), nullable=True)
    retention_id = Column(Integer, ForeignKey("retention_policies.id"), nullable=True)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    storage = relationship("StorageBackend", lazy="joined")
    schedule = relationship("Schedule", lazy="joined")
    retention = relationship("RetentionPolicy", lazy="joined")


# ---------------------------------------------------------------------------
# Backup Records  (history of executed backups)
# ---------------------------------------------------------------------------
class BackupRecord(Base):
    __tablename__ = "backup_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("backup_jobs.id"), nullable=False)
    status = Column(String, nullable=False)  # running | success | error | warning
    size_bytes = Column(BigInteger, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    file_path = Column(String, nullable=True)  # local temp path (may be cleaned up)
    storage_path = Column(String, nullable=True)  # remote/final path
    started_at = Column(DateTime, nullable=False, default=_utcnow)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    # JSON-encoded lists
    containers_stopped = Column(Text, nullable=True)
    volumes_backed_up = Column(Text, nullable=True)

    job = relationship("BackupJob", lazy="joined")


# ---------------------------------------------------------------------------
# Log Entries
# ---------------------------------------------------------------------------
class LogEntry(Base):
    __tablename__ = "log_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    level = Column(String, nullable=False)  # info | success | warning | error
    job_name = Column(String, nullable=True)
    message = Column(String, nullable=False)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utcnow)


# ---------------------------------------------------------------------------
# Notification Channels
# ---------------------------------------------------------------------------
class NotificationChannel(Base):
    __tablename__ = "notification_channels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)  # email | slack | webhook
    config_json = Column(Text, nullable=False, default="{}")
    events_json = Column(Text, nullable=False, default="[]")  # ["failure","warning","success"]
    enabled = Column(Boolean, default=True)
    last_triggered_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


# ---------------------------------------------------------------------------
# Settings (key-value store)
# ---------------------------------------------------------------------------
class Setting(Base):
    __tablename__ = "settings"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=True)  # JSON-encoded
