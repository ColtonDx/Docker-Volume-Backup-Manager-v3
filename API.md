# Docker Volume Backup Manager — API Reference

All endpoints are prefixed with `/api`. Most endpoints require a Bearer token obtained from `/api/auth/login`.

**Base URL:** `http://<host>:8000/api`

---

## Authentication

### `POST /auth/login`

Authenticate and receive a JWT token. No auth header required.

**Request body:**
```json
{ "password": "admin" }
```

**Response `200`:**
```json
{ "token": "<jwt>" }
```

All subsequent requests must include:
```
Authorization: Bearer <token>
```

---

## Dashboard

### `GET /dashboard`

Returns aggregate stats for the UI dashboard.

**Response `200`:**
```json
{
  "total_jobs": 3,
  "active_jobs": 2,
  "storage_backends_count": 1,
  "success_rate_30d": 97.5,
  "active_alerts": 0,
  "recent_jobs": [ /* BackupRecord[] */ ],
  "upcoming_schedules": [
    { "id": 1, "name": "nightly", "cron": "0 2 * * *", "next_run": "...", "job_names": ["web"] }
  ]
}
```

---

## Backup Jobs

### `GET /jobs`

List all backup jobs with live status, matched containers, and schedule info.

**Response `200`:** `BackupJob[]`

---

### `GET /jobs/{job_id}`

Get a single backup job.

**Response `200`:** `BackupJob`  
**Response `404`:** Job not found

---

### `POST /jobs`

Create a new backup job.

**Request body:**
```json
{
  "name": "my-app",
  "label_key": "dvbm.job",
  "label_value": "my-app",
  "storage_id": 1,
  "schedule_id": 1,
  "retention_id": 1,
  "enabled": true,
  "timeout_seconds": null
}
```

`label_value` defaults to `name` if omitted. `schedule_id`, `retention_id`, and `timeout_seconds` are optional.

**Response `201`:** `BackupJob`

---

### `PUT /jobs/{job_id}`

Update an existing backup job. All fields are optional (partial update).

**Request body:** same fields as `POST /jobs`, all optional.

**Response `200`:** `BackupJob`  
**Response `404`:** Job not found

---

### `DELETE /jobs/{job_id}`

Delete a backup job.

**Response `204`:** No content  
**Response `404`:** Job not found

---

### `POST /jobs/{job_id}/run`

Manually trigger a backup job immediately (runs in background).

**Response `200`:**
```json
{ "message": "Backup job 'my-app' triggered" }
```

---

### `POST /jobs/{job_id}/pause`

Disable a job (stops scheduled runs).

**Response `200`:**
```json
{ "message": "Job 'my-app' paused" }
```

---

### `POST /jobs/{job_id}/resume`

Re-enable a paused job.

**Response `200`:**
```json
{ "message": "Job 'my-app' resumed" }
```

---

### `GET /jobs/{job_id}/stats`

Detailed stats for a single job: success rate, backup history, recent logs, next scheduled run.

**Response `200`:**
```json
{
  "job": { /* BackupJob */ },
  "success_rate_30d": 95.0,
  "total_backups": 42,
  "total_size_bytes": 1073741824,
  "avg_duration_seconds": 12.4,
  "errors_24h": 0,
  "recent_backups": [ /* BackupRecord[] (last 20) */ ],
  "logs": [ /* LogEntry[] (last 50) */ ],
  "schedule_info": { "name": "nightly", "cron": "0 2 * * *", "next_run": "..." }
}
```

---

## Schedules

### `GET /schedules`

List all cron schedules.

**Response `200`:** `Schedule[]`

---

### `GET /schedules/{schedule_id}`

Get a single schedule.

**Response `200`:** `Schedule`  
**Response `404`:** Schedule not found

---

### `POST /schedules`

Create a schedule. `cron` uses standard 5-field cron syntax (`min hour day month weekday`).

**Request body:**
```json
{
  "name": "nightly",
  "cron": "0 2 * * *",
  "description": "Every night at 2am",
  "enabled": true
}
```

**Response `201`:** `Schedule`

---

### `PUT /schedules/{schedule_id}`

Update a schedule. All fields optional.

**Response `200`:** `Schedule`  
**Response `404`:** Schedule not found

---

### `DELETE /schedules/{schedule_id}`

Delete a schedule. Any jobs linked to it are detached (they become manual-only).

**Response `204`:** No content  
**Response `404`:** Schedule not found

---

## Storage Backends

Supported types: `localfs`, `s3`, `ftp`, `sftp`, `rclone`

### `GET /storages`

List all storage backends.

**Response `200`:** `StorageBackend[]`

---

### `GET /storages/rclone/remotes`

List configured rclone remotes from the rclone binary.

**Response `200`:**
```json
{ "remotes": ["myremote", "gdrive"] }
```

---

### `GET /storages/{storage_id}`

Get a single storage backend.

**Response `200`:** `StorageBackend`  
**Response `404`:** Not found

---

### `POST /storages`

Create a storage backend.

**Request body:**
```json
{
  "name": "my-s3",
  "type": "s3",
  "config": {
    "bucket": "my-bucket",
    "region": "us-east-1",
    "access_key": "...",
    "secret_key": "...",
    "prefix": "backups/"
  }
}
```

**Config fields by type:**

| Type | Required fields | Optional fields |
|------|----------------|-----------------|
| `localfs` | `path` | — |
| `s3` | `bucket`, `access_key`, `secret_key` | `region`, `endpoint`, `prefix` |
| `ftp` | `host`, `user`, `password` | `port` (default 21), `path` |
| `sftp` | `host`, `user` | `password`, `key_path`, `port` (default 22), `path` |
| `rclone` | `remote` | `path`, `flags` |

**Response `201`:** `StorageBackend`  
**Response `409`:** Name already in use

---

### `PUT /storages/{storage_id}`

Update a storage backend. All fields optional.

**Response `200`:** `StorageBackend`  
**Response `404`:** Not found  
**Response `409`:** Name conflict

---

### `DELETE /storages/{storage_id}`

Delete a storage backend.

**Response `204`:** No content  
**Response `404`:** Not found

---

### `POST /storages/{storage_id}/test`

Test connectivity to a storage backend.

**Response `200`:**
```json
{ "success": true, "message": "Connection successful" }
```

---

## Retention Policies

### `GET /rotations`

List all retention policies.

**Response `200`:** `RetentionPolicy[]`

---

### `GET /rotations/{policy_id}`

Get a single policy.

**Response `200`:** `RetentionPolicy`  
**Response `404`:** Not found

---

### `POST /rotations`

Create a retention policy.

**Request body:**
```json
{
  "name": "keep-30d",
  "description": "Keep backups for 30 days",
  "retention_days": 30,
  "min_backups": 3,
  "max_backups": 50
}
```

`min_backups` defaults to `1`. `max_backups` is optional (no hard cap if omitted).

**Response `201`:** `RetentionPolicy`

---

### `PUT /rotations/{policy_id}`

Update a retention policy. All fields optional.

**Response `200`:** `RetentionPolicy`  
**Response `404`:** Not found

---

### `DELETE /rotations/{policy_id}`

Delete a retention policy.

**Response `204`:** No content  
**Response `404`:** Not found

---

### `POST /rotations/{policy_id}/run`

Manually trigger retention cleanup for a policy right now.

**Response `200`:**
```json
{ "message": "Cleanup complete. Removed 3 backup(s)." }
```

---

## Backup Records

### `GET /backups`

List backup records, newest first.

**Query params:**

| Param | Type | Description |
|-------|------|-------------|
| `job_id` | int | Filter by job |
| `status` | string | `success`, `error`, `warning`, `running` |
| `limit` | int | Max results (default `100`, max `500`) |
| `offset` | int | Pagination offset |

**Response `200`:** `BackupRecord[]`

---

### `GET /backups/{backup_id}`

Get a single backup record.

**Response `200`:** `BackupRecord`  
**Response `404`:** Not found

---

### `POST /backups/{backup_id}/restore`

Restore volumes from a backup record. Only works on `status = "success"` records.

**Response `200`:**
```json
{ "message": "Restore initiated from backup #42" }
```

**Response `400`:** Not a successful backup  
**Response `404`:** Not found

---

### `DELETE /backups/{backup_id}`

Delete a backup record (does not delete the file from storage).

**Response `204`:** No content  
**Response `404`:** Not found

---

### `POST /backups/import?job_id={job_id}`

Scan a job's storage backend for existing `.tar.gz` archive files and import them as backup records. Skips archives already tracked in the database.

**Query params:**

| Param | Type | Required |
|-------|------|----------|
| `job_id` | int | Yes |

**Response `200`:**
```json
{
  "imported": 5,
  "skipped": 2,
  "total_found": 7,
  "message": "Imported 5 backup(s), skipped 2 already known"
}
```

---

## Logs

### `GET /logs`

List log entries, newest first.

**Query params:**

| Param | Type | Description |
|-------|------|-------------|
| `level` | string | `info`, `success`, `warning`, `error` |
| `job_name` | string | Filter by job name |
| `search` | string | Substring search on message and job name |
| `limit` | int | Max results (default `200`, max `1000`) |
| `offset` | int | Pagination offset |

**Response `200`:** `LogEntry[]`

---

### `DELETE /logs`

Clear log entries.

**Query params:**

| Param | Type | Description |
|-------|------|-------------|
| `level` | string | If set, only deletes logs at this level |

**Response `204`:** No content

---

## Notification Channels

Supported types: `email`, `slack`, `discord`, `gotify`, `ntfy`, `webhook`

### `GET /notifications`

List all notification channels.

**Response `200`:** `NotificationChannel[]`

---

### `GET /notifications/{channel_id}`

Get a single channel.

**Response `200`:** `NotificationChannel`  
**Response `404`:** Not found

---

### `POST /notifications`

Create a notification channel.

**Request body:**
```json
{
  "name": "my-discord",
  "type": "discord",
  "config": {
    "webhook_url": "https://discord.com/api/webhooks/..."
  },
  "events": ["backup_success", "backup_failure"],
  "enabled": true
}
```

**Events:** `backup_success`, `backup_failure`, `backup_warning`, `restore_success`, `restore_failure`

**Config fields by type:**

| Type | Fields |
|------|--------|
| `email` | `smtp_host`, `smtp_port`, `smtp_user`, `smtp_password`, `from_addr`, `to_addr`, `use_tls` |
| `slack` | `webhook_url` |
| `discord` | `webhook_url` |
| `gotify` | `url`, `token` |
| `ntfy` | `url`, `topic` |
| `webhook` | `url`, `method` (default `POST`), `headers` (object) |

**Response `201`:** `NotificationChannel`

---

### `PUT /notifications/{channel_id}`

Update a channel. All fields optional.

**Response `200`:** `NotificationChannel`  
**Response `404`:** Not found

---

### `DELETE /notifications/{channel_id}`

Delete a notification channel.

**Response `204`:** No content  
**Response `404`:** Not found

---

### `POST /notifications/{channel_id}/test`

Send a test notification through the channel.

**Response `200`:**
```json
{ "success": true, "message": "Test notification sent" }
```

---

## Settings

### `GET /settings`

Get all application settings as a flat key-value map.

**Response `200`:**
```json
{
  "settings": {
    "timezone": "America/New_York",
    "default_label_key": "dvbm.job",
    "rclone_enabled": false,
    "default_compression": "gzip",
    "default_encryption": "none",
    "verify_backups": true,
    "parallel_uploads": true,
    "notify_on_success": false,
    "notify_on_warning": true,
    "notify_on_failure": true,
    "log_retention_backup_days": 30,
    "log_retention_system_days": 14,
    "syslog_enabled": false,
    "instance_name": "DVBM"
  }
}
```

---

### `PUT /settings`

Update one or more settings. Send the full `settings` map or just the keys you want to change.

**Request body:**
```json
{
  "settings": {
    "timezone": "America/Chicago",
    "notify_on_failure": true
  }
}
```

**Response `200`:** Updated `SettingsBundle` (same shape as `GET /settings`)

---

### `POST /settings/reset`

Reset all settings to their defaults.

**Response `200`:** Default `SettingsBundle`

---

### `GET /settings/export`

Download all configuration (jobs, schedules, storages, retention policies, notifications, settings) as a `.zip` file.

**Response `200`:** `application/zip` file download (`dvbm_config_<timestamp>.zip`)

---

### `POST /settings/import`

Import configuration from a `.zip` file exported by `GET /settings/export`. Existing records are upserted by primary key.

**Request:** `multipart/form-data` with a `file` field containing the `.zip`.

**Response `200`:**
```json
{
  "status": "ok",
  "imported": {
    "settings": 14,
    "storage_backends": 1,
    "schedules": 2,
    "retention_policies": 1,
    "notification_channels": 2,
    "backup_jobs": 3
  }
}
```

---

## Data Schemas

### BackupJob

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | — |
| `name` | string | Job name (matches Docker label value by default) |
| `label_key` | string | Docker label key (default: `dvbm.job`) |
| `label_value` | string | Docker label value |
| `label` | string | Computed `key=value` string |
| `enabled` | bool | Whether job runs on schedule |
| `timeout_seconds` | int\|null | Per-job timeout override |
| `storage` | StorageBackend\|null | Linked storage backend |
| `schedule` | Schedule\|null | Linked cron schedule |
| `retention` | RetentionPolicy\|null | Linked retention policy |
| `containers` | string[] | Live-matched Docker container names |
| `status` | string | `idle`, `active`, `running`, `error` |
| `last_run` | string\|null | ISO datetime of last run |
| `next_run` | string\|null | Cron expression note |
| `created_at` | datetime | — |
| `updated_at` | datetime | — |

### BackupRecord

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | — |
| `job_id` | int | — |
| `job_name` | string | — |
| `status` | string | `success`, `error`, `warning`, `running` |
| `size_bytes` | int\|null | Archive file size |
| `duration_seconds` | float\|null | — |
| `file_path` | string\|null | Local staging path (temp) |
| `storage_path` | string\|null | Path on the storage backend |
| `started_at` | datetime | — |
| `completed_at` | datetime\|null | — |
| `error_message` | string\|null | — |
| `containers_stopped` | string[] | Container names stopped during backup |
| `volumes_backed_up` | string[] | Volume names included in archive |

### Schedule

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | — |
| `name` | string | — |
| `cron` | string | 5-field cron expression |
| `description` | string\|null | — |
| `enabled` | bool | — |
| `job_count` | int | Number of jobs using this schedule |
| `created_at` | datetime | — |
| `updated_at` | datetime | — |

### StorageBackend

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | — |
| `name` | string | — |
| `type` | string | `localfs`, `s3`, `ftp`, `sftp`, `rclone` |
| `config` | object | Type-specific connection config |
| `created_at` | datetime | — |
| `updated_at` | datetime | — |

### RetentionPolicy

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | — |
| `name` | string | — |
| `description` | string\|null | — |
| `retention_days` | int | Delete backups older than N days |
| `min_backups` | int | Always keep at least N backups |
| `max_backups` | int\|null | Cap total backups at N |
| `job_count` | int | Number of jobs using this policy |
| `created_at` | datetime | — |
| `updated_at` | datetime | — |

### NotificationChannel

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | — |
| `name` | string | — |
| `type` | string | `email`, `slack`, `discord`, `gotify`, `ntfy`, `webhook` |
| `config` | object | Type-specific config |
| `events` | string[] | Events that trigger this channel |
| `enabled` | bool | — |
| `last_triggered_at` | datetime\|null | — |
| `created_at` | datetime | — |
| `updated_at` | datetime | — |

### LogEntry

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | — |
| `level` | string | `info`, `success`, `warning`, `error` |
| `job_name` | string\|null | — |
| `message` | string | — |
| `details` | string\|null | Extended detail text |
| `created_at` | datetime | — |

---

## Automation Example

```bash
BASE=http://localhost:8000/api

# 1. Authenticate
TOKEN=$(curl -s -X POST "$BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"password":"admin"}' | jq -r .token)

AUTH="Authorization: Bearer $TOKEN"

# 2. List jobs
curl -s "$BASE/jobs" -H "$AUTH" | jq .

# 3. Trigger a specific job by ID
curl -s -X POST "$BASE/jobs/1/run" -H "$AUTH" | jq .

# 4. Poll for completion
curl -s "$BASE/backups?job_id=1&limit=1" -H "$AUTH" | jq '.[0].status'

# 5. List recent errors
curl -s "$BASE/logs?level=error&limit=20" -H "$AUTH" | jq .
```
