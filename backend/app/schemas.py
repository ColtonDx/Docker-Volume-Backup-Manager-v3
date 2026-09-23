"""Pydantic schemas for request/response serialization."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, field_validator, model_validator


def _validate_cron(value: str) -> str:
    """Reject cron expressions APScheduler cannot parse.

    An invalid expression previously saved fine and then failed silently at
    schedule time, so the job simply never fired.
    """
    from apscheduler.triggers.cron import CronTrigger

    parts = (value or "").split()
    if len(parts) != 5:
        raise ValueError(
            "Cron expression must have 5 fields (minute hour day month day_of_week)"
        )
    try:
        CronTrigger(
            minute=parts[0], hour=parts[1], day=parts[2],
            month=parts[3], day_of_week=parts[4],
        )
    except Exception as exc:
        raise ValueError(f"Invalid cron expression: {exc}") from exc
    return value


def _validate_safe_name(value: str) -> str:
    """Names end up in archive filenames, so keep them path-safe."""
    import re

    if not value or not value.strip():
        raise ValueError("Name must not be empty")
    if not re.fullmatch(r"[A-Za-z0-9 ._-]+", value):
        raise ValueError(
            "Name may only contain letters, numbers, spaces, dots, hyphens and underscores"
        )
    return value.strip()


# ---- Auth ----------------------------------------------------------------

class LoginRequest(BaseModel):
    password: str


class TokenResponse(BaseModel):
    token: str


# ---- Storage Backends ----------------------------------------------------

class StorageBackendBase(BaseModel):
    name: str
    type: str  # localfs | s3 | ftp | rclone
    config: dict[str, Any] = {}


class StorageBackendCreate(StorageBackendBase):
    pass


class StorageBackendUpdate(BaseModel):
    name: str | None = None
    type: str | None = None
    config: dict[str, Any] | None = None


class StorageBackendOut(StorageBackendBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

    @model_validator(mode="before")
    @classmethod
    def parse_config_json(cls, data: Any) -> Any:
        if hasattr(data, "config_json"):
            try:
                raw = data.config_json if isinstance(data.config_json, str) else "{}"
                parsed = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                parsed = {}
            from app.secrets_mask import mask_config
            # Build a dict representation so Pydantic can work with it
            return {
                "id": data.id,
                "name": data.name,
                "type": data.type,
                "config": mask_config(parsed),
                "created_at": data.created_at,
                "updated_at": data.updated_at,
            }
        return data


# ---- Schedules -----------------------------------------------------------

class ScheduleBase(BaseModel):
    name: str
    cron: str
    description: str | None = None
    enabled: bool = True

    @field_validator("cron")
    @classmethod
    def _check_cron(cls, v: str) -> str:
        return _validate_cron(v)


class ScheduleCreate(ScheduleBase):
    pass


class ScheduleUpdate(BaseModel):
    name: str | None = None
    cron: str | None = None
    description: str | None = None
    enabled: bool | None = None

    @field_validator("cron")
    @classmethod
    def _check_cron(cls, v: str | None) -> str | None:
        return _validate_cron(v) if v is not None else v


class ScheduleOut(ScheduleBase):
    id: int
    job_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ---- Retention Policies --------------------------------------------------

class RetentionPolicyBase(BaseModel):
    name: str
    description: str | None = None
    retention_days: int
    # Floor of 1: a policy must never be able to delete a job's last backup.
    min_backups: int = 1
    max_backups: int | None = None

    @field_validator("min_backups")
    @classmethod
    def _min_backups_floor(cls, v: int) -> int:
        if v < 1:
            raise ValueError("min_backups must be at least 1")
        return v

    @model_validator(mode="after")
    def _max_not_below_min(self):
        if self.max_backups is not None and self.max_backups < self.min_backups:
            raise ValueError("max_backups must be greater than or equal to min_backups")
        return self


class RetentionPolicyCreate(RetentionPolicyBase):
    pass


class RetentionPolicyUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    retention_days: int | None = None
    min_backups: int | None = None
    max_backups: int | None = None

    @field_validator("min_backups")
    @classmethod
    def _min_backups_floor(cls, v: int | None) -> int | None:
        if v is not None and v < 1:
            raise ValueError("min_backups must be at least 1")
        return v


class RetentionPolicyOut(RetentionPolicyBase):
    id: int
    job_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ---- Backup Jobs ---------------------------------------------------------

class BackupJobBase(BaseModel):
    name: str
    label_key: str = "dvbm.job"
    label_value: str = ""
    storage_id: int
    schedule_id: int | None = None
    retention_id: int | None = None
    enabled: bool = True
    timeout_seconds: int | None = None  # None = use JOB_TIMEOUT_SECONDS global default

    # The job name becomes part of the archive filename, so "/" or ".." in it
    # would steer where the upload lands.
    @field_validator("name")
    @classmethod
    def _check_name(cls, v: str) -> str:
        return _validate_safe_name(v)


class BackupJobCreate(BackupJobBase):
    pass


class BackupJobUpdate(BaseModel):
    name: str | None = None
    label_key: str | None = None
    label_value: str | None = None
    storage_id: int | None = None
    schedule_id: int | None = None
    retention_id: int | None = None
    enabled: bool | None = None
    timeout_seconds: int | None = None

    @field_validator("name")
    @classmethod
    def _check_name(cls, v: str | None) -> str | None:
        return _validate_safe_name(v) if v is not None else v


class BackupJobOut(BaseModel):
    id: int
    name: str
    label_key: str = "dvbm.job"
    label_value: str = ""
    label: str = ""  # computed: "{label_key}={label_value}"
    enabled: bool
    timeout_seconds: int | None = None
    storage: StorageBackendOut | None = None
    schedule: ScheduleOut | None = None
    retention: RetentionPolicyOut | None = None
    containers: list[str] = []  # filled dynamically from Docker
    status: str = "idle"  # filled dynamically
    last_run: str | None = None
    next_run: str | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ---- Backup Records ------------------------------------------------------

class BackupRecordOut(BaseModel):
    id: int
    job_id: int
    job_name: str = ""
    status: str
    size_bytes: int | None = None
    duration_seconds: float | None = None
    file_path: str | None = None
    storage_path: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    error_message: str | None = None
    containers_stopped: list[str] = []
    volumes_backed_up: list[str] = []

    class Config:
        from_attributes = True

    @model_validator(mode="before")
    @classmethod
    def parse_json_fields(cls, data: Any) -> Any:
        if hasattr(data, "containers_stopped"):
            d: dict[str, Any] = {
                "id": data.id,
                "job_id": data.job_id,
                "job_name": data.job.name if data.job else "",
                "status": data.status,
                "size_bytes": data.size_bytes,
                "duration_seconds": data.duration_seconds,
                "file_path": data.file_path,
                "storage_path": data.storage_path,
                "started_at": data.started_at,
                "completed_at": data.completed_at,
                "error_message": data.error_message,
            }
            try:
                d["containers_stopped"] = json.loads(data.containers_stopped or "[]")
            except (json.JSONDecodeError, TypeError):
                d["containers_stopped"] = []
            try:
                d["volumes_backed_up"] = json.loads(data.volumes_backed_up or "[]")
            except (json.JSONDecodeError, TypeError):
                d["volumes_backed_up"] = []
            return d
        return data


# ---- Log Entries ---------------------------------------------------------

class LogEntryOut(BaseModel):
    id: int
    level: str
    job_name: str | None = None
    message: str
    details: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


# ---- Notification Channels -----------------------------------------------

class NotificationChannelBase(BaseModel):
    name: str
    type: str  # email | slack | discord | gotify | ntfy | webhook
    config: dict[str, Any] = {}
    events: list[str] = []
    enabled: bool = True


class NotificationChannelCreate(NotificationChannelBase):
    pass


class NotificationChannelUpdate(BaseModel):
    name: str | None = None
    type: str | None = None
    config: dict[str, Any] | None = None
    events: list[str] | None = None
    enabled: bool | None = None


class NotificationChannelOut(NotificationChannelBase):
    id: int
    last_triggered_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

    @model_validator(mode="before")
    @classmethod
    def parse_json_fields(cls, data: Any) -> Any:
        if hasattr(data, "config_json"):
            d: dict[str, Any] = {
                "id": data.id,
                "name": data.name,
                "type": data.type,
                "enabled": data.enabled,
                "last_triggered_at": data.last_triggered_at,
                "created_at": data.created_at,
                "updated_at": data.updated_at,
            }
            try:
                from app.secrets_mask import mask_config
                d["config"] = mask_config(json.loads(data.config_json or "{}"))
            except (json.JSONDecodeError, TypeError):
                d["config"] = {}
            try:
                d["events"] = json.loads(data.events_json or "[]")
            except (json.JSONDecodeError, TypeError):
                d["events"] = []
            return d
        return data


# ---- Settings ------------------------------------------------------------

class SettingItem(BaseModel):
    key: str
    value: Any = None


class SettingsBundle(BaseModel):
    """Flat dictionary of all settings."""
    settings: dict[str, Any] = {}


# ---- Dashboard -----------------------------------------------------------

class DashboardStats(BaseModel):
    total_jobs: int = 0
    active_jobs: int = 0
    total_storage_used_bytes: int = 0
    storage_backends_count: int = 0
    success_rate_30d: float = 0.0
    active_alerts: int = 0
    recent_jobs: list[BackupRecordOut] = []
    upcoming_schedules: list[dict[str, Any]] = []
    storage_usage: list[dict[str, Any]] = []


class JobDetailStats(BaseModel):
    job: BackupJobOut
    success_rate_30d: float = 0.0
    total_backups: int = 0
    total_size_bytes: int = 0
    avg_duration_seconds: float | None = None
    errors_24h: int = 0
    recent_backups: list[BackupRecordOut] = []
    logs: list[LogEntryOut] = []
    schedule_info: dict[str, Any] | None = None


