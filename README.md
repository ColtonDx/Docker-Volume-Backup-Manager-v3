# Docker Volume Backup Manager v3

A self-hosted web app for backing up Docker container volumes. It stops the target containers, archives their volumes into a `.tar.gz`, uploads the archive to your chosen storage backend, restarts the containers, and records the result. Everything is configured through a browser UI. The whole thing runs as a single Docker container.

---

## Table of Contents

- [How it works](#how-it-works)
- [Quick start](#quick-start)
- [Labelling containers](#labelling-containers)
- [Docker Compose configuration](#docker-compose-configuration)
- [UI settings reference](#ui-settings-reference)
- [Features in detail](#features-in-detail)
  - [Backup jobs](#backup-jobs)
  - [Schedules](#schedules)
  - [Storage backends](#storage-backends)
  - [Retention policies](#retention-policies)
  - [Notifications](#notifications)
  - [Job queue and concurrency](#job-queue-and-concurrency)
  - [Restore](#restore)
  - [Config backup](#config-backup)
  - [Syslog forwarding](#syslog-forwarding)
- [API reference](#api-reference)
- [Data persistence](#data-persistence)
- [TLS / HTTPS](#tls--https)
- [Database encryption](#database-encryption)

---

## How it works

1. You create a **Backup Job** in the UI and give it a name, a storage backend, and optionally a schedule and retention policy.
2. You add a Docker label to the containers you want backed up. The label value must match the job name.
3. When a backup runs (on schedule or manually), the app:
   - Finds all containers with that label.
   - Collects the named volumes attached to those containers.
   - Stops the running containers.
   - Exports each volume using a temporary Alpine helper container and bundles everything into a `.tar.gz` archive.
   - Uploads the archive to the configured storage backend.
   - Restarts the containers.
   - Records the result (size, duration, status) in the database.
   - Runs the retention policy if one is configured.
   - Sends notifications if any channels are subscribed to the outcome.

If a backup fails after containers have already been stopped, the containers are **not** automatically restarted. They will need to be started manually, or they will start again on the next scheduled backup run.

---

## Quick start

```bash
# Clone or download the repo, then edit docker-compose.yml:
# Set APP_PASSWORD to something other than "changeme"

docker compose up -d

# Open the UI at:
# https://localhost:8000
# Accept the self-signed certificate warning, or import /data/certs/cert.pem
# into your OS or browser trust store.
```

---

## Labelling containers

The app matches containers to backup jobs using a Docker label. Add the label to any container you want included in a job:

```yaml
# In your application's docker-compose.yml (not this one)
services:
  myapp:
    image: myapp:latest
    labels:
      - "dvbm.job=myapp"   # The value must match the Job Name set in the UI
```

The label key (`dvbm.job`) can be changed in Settings or via the `DOCKER_LABEL_KEY` environment variable. Multiple containers can share the same label value, in which case all of them are stopped and their volumes are included in the same archive.

---

## Docker Compose configuration

```yaml
services:
  docker-volume-backup-manager:
    image: coltondx/docker-volume-backup-manager-v3:latest
    container_name: docker-volume-backup-manager
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      # Required: gives the app access to manage Docker containers
      - /var/run/docker.sock:/var/run/docker.sock

      # Required: stores the SQLite database and auto-generated TLS certs
      - data:/data

      # Required: staging area for building archives before upload
      - temp:/backups

      # Optional: a host directory for local filesystem backups
      - ./local-backups:/local-backups

      # Optional: bring your own rclone config instead of pasting it in the UI
      # - ~/.config/rclone:/root/.config/rclone:ro

    environment:
      # Login password for the web UI. Change this.
      - APP_PASSWORD=changeme

      # Signs JWT session tokens. Use a long random string in production.
      # If not set, a hardcoded default is used (insecure).
      # - JWT_SECRET=replace-with-something-random

      # How long a login session lasts, in hours. Default: 24.
      # - JWT_EXPIRE_HOURS=24

      # Name shown in the sidebar. Default: Docker Volume Backup Manager.
      # - APP_NAME=Docker Volume Backup Manager

      # Docker label key used to match containers to jobs. Default: dvbm.job.
      # - DOCKER_LABEL_KEY=dvbm.job

      # Maximum number of backup or restore jobs that run at the same time.
      # Default is 1, meaning jobs run one at a time. If a job is triggered
      # while another is running, it waits in a queue. Increasing this is only
      # safe if your jobs target completely separate containers with no shared volumes.
      # - MAX_CONCURRENT_BACKUPS=1

      # How long a single backup or restore job can run before it is marked as
      # failed and the slot is released. In seconds. Default: 7200 (2 hours).
      # Set to 0 to disable (not recommended -- a hung job will block the queue forever).
      # Per-job timeouts can also be set individually in the UI and take priority over this.
      # - JOB_TIMEOUT_SECONDS=7200

      # Timezone used by the scheduler when evaluating cron expressions.
      # Must be a valid IANA timezone name, e.g. America/New_York, Europe/London.
      # Default: UTC.
      # - TZ=UTC

      # Encrypt the SQLite database on disk using AES-256 (SQLCipher).
      # If an existing plaintext database is found when this is first set,
      # it will be migrated automatically. A backup is saved as dvbm.db.plaintext.bak.
      # WARNING: if you lose this key, the database is permanently unreadable.
      # - DB_ENCRYPTION_KEY=replace-with-a-strong-passphrase

      # Comma-separated list of Host header values to accept.
      # Default is * (any). Restrict this if the app is publicly accessible.
      # Example: ALLOWED_HOSTS=myhost.example.com,localhost
      # - ALLOWED_HOSTS=*

      # Comma-separated list of CORS origins to accept.
      # Default is * (any). Restrict this if you have a separate frontend origin.
      # Example: ALLOWED_ORIGINS=https://myhost.example.com
      # - ALLOWED_ORIGINS=*

      # Set to false to serve the app over plain HTTP instead of HTTPS.
      # - SSL_ENABLED=true

      # Path to a custom TLS certificate file. If not set, a self-signed cert
      # is generated automatically on first start and stored in /data/certs/.
      # - SSL_CERT_FILE=/data/certs/fullchain.pem

      # Path to the private key for the custom certificate above.
      # - SSL_KEY_FILE=/data/certs/privkey.pem

      # Path where the auto-generated cert and key are stored. Default: /data/certs.
      # - SSL_CERT_DIR=/data/certs

volumes:
  data:
  temp:
```

### Volume mounts

| Mount | Required | Purpose |
|---|---|---|
| `/var/run/docker.sock` | Yes | Lets the app start, stop, and inspect Docker containers. |
| `/data` | Yes | Stores the SQLite database and auto-generated TLS certificates. Use a named volume to persist this. |
| `/backups` | Yes | Temporary staging directory used while building archives. Files here are deleted after each upload. Does not need to persist. |
| `/local-backups` (or any path) | Optional | If you use the local filesystem storage backend, bind-mount a host directory here and set the storage path to match. |
| `~/.config/rclone` | Optional | Mount an existing rclone config instead of pasting it into the UI. |

---

## UI settings reference

Settings are configured through the Settings page in the UI. They are stored in the database.

### General

| Setting | Default | Description |
|---|---|---|
| Timezone | UTC | The timezone used when evaluating cron schedules. Must match an IANA timezone name (e.g. `America/Chicago`). Changes take effect immediately -- the scheduler restarts with the new timezone. |
| Default Label Key | `dvbm.job` | The Docker label key used to match containers to jobs. This is a global default; individual jobs can override it. |
| Default Compression | `gzip` | Compression used when building archives. |

### Rclone

| Setting | Default | Description |
|---|---|---|
| Enable rclone | Off | Enables the rclone storage backend option when creating storage backends. |
| rclone Binary | `/usr/bin/rclone` | Path to the rclone executable inside the container. rclone is bundled in the image. |
| rclone Config Path | `/root/.config/rclone/rclone.conf` | Where rclone looks for its config file. |
| rclone Config (text) | Empty | Paste your `rclone.conf` content here. It is written to the config path above on save. This is the easiest way to configure rclone without bind-mounting the config file. |
| rclone Flags | Empty | Extra CLI flags passed to every rclone command (e.g. `--transfers 4`). |

### Backup behavior

| Setting | Default | Description |
|---|---|---|
| Verify backups | On | After uploading, downloads a portion of the file and checks the size. Catches silent upload failures. |
| Parallel uploads | On | Allows upload operations to run concurrently when the archive is large. |

### Notifications

| Setting | Default | Description |
|---|---|---|
| Notify on success | Off | Send a notification when a backup completes successfully. |
| Notify on warning | On | Send a notification when a backup completes with warnings. |
| Notify on failure | On | Send a notification when a backup fails. |

### Log retention

| Setting | Default | Description |
|---|---|---|
| Backup log retention | 30 days | Log entries related to backup jobs older than this are automatically purged. |
| System log retention | 14 days | System-level log entries older than this are automatically purged. |

### Syslog

| Setting | Default | Description |
|---|---|---|
| Enable syslog | Off | Forwards application log entries to a remote syslog server. |
| Syslog host | Empty | Hostname or IP of the syslog server. |
| Syslog port | 514 | UDP or TCP port the syslog server listens on. |
| Syslog protocol | UDP | Transport protocol. Options: UDP, TCP. |
| Syslog facility | local0 | The syslog facility code. Typical options: local0 through local7. |

### Config backup

| Setting | Default | Description |
|---|---|---|
| Enable config backup | Off | Automatically exports the app configuration as a `.zip` file on a schedule and uploads it to a storage backend. |
| Storage backend | None | Which storage backend to upload the config backup to. |
| Schedule | None | Which cron schedule to use for the config backup. |
| Notification channel | None | A notification channel to alert on config backup results. |
| Retention policy | None | A retention policy to apply to the config backup files in storage. |

---

## Features in detail

### Backup jobs

A backup job defines what gets backed up and where. Each job has:

- **Name** -- used as the label value when matching containers. Must be unique.
- **Docker Label** -- the key=value pair used to find containers. Defaults to `dvbm.job=<job name>`. You can override both the key and value per job.
- **Storage backend** -- where the archive is uploaded.
- **Schedule** -- optional cron schedule that triggers the job automatically.
- **Retention policy** -- optional cleanup policy run after each successful backup.
- **Timeout** -- optional per-job timeout in seconds. Overrides the global `JOB_TIMEOUT_SECONDS`.

**How a backup runs:**

1. Find all containers with the matching label (including stopped ones).
2. Collect the named Docker volumes attached to those containers. Duplicate volumes are deduplicated.
3. Stop any containers that are currently running.
4. For each volume, spin up a temporary `alpine` container with the volume mounted, tar the contents into a staging directory, and remove the helper container.
5. Bundle all exported volume directories into a single `.tar.gz` archive named `<job_name>_<timestamp>.tar.gz`.
6. Upload the archive to the configured storage backend.
7. Restart the containers that were stopped.
8. Write a record to the database with size, duration, file path, and status.
9. Delete the archive from the staging directory.
10. Apply the retention policy if one is set.
11. Send notifications.

If no containers match the label, the job fails immediately. Containers are not stopped first in this case, so there is no disruption.

### Schedules

Schedules use standard 5-field cron expressions: `minute hour day_of_month month day_of_week`.

Examples:

| Expression | Meaning |
|---|---|
| `0 2 * * *` | Every day at 2:00 AM |
| `0 */6 * * *` | Every 6 hours |
| `30 3 * * 0` | Every Sunday at 3:30 AM |
| `0 0 1 * *` | First day of every month at midnight |

Schedules are shared resources. The same schedule can be assigned to multiple jobs and to the config backup. Creating or editing a schedule does not affect any jobs using it until the scheduler is synced (which happens automatically on save).

The scheduler uses the timezone set in Settings. If you change the timezone, the scheduler restarts immediately with the new setting and recalculates all next-run times.

### Storage backends

#### Local filesystem

Stores archives in a directory on disk inside the container. To make backups survive container restarts, bind-mount a host directory to the path you configure (e.g. `/local-backups`).

Configuration fields:
- **Path** -- absolute path inside the container where archives are written.

#### Amazon S3 / S3-compatible

Uploads archives to an S3 bucket. Works with AWS S3 and any S3-compatible service (MinIO, Backblaze B2, Cloudflare R2, etc.).

Configuration fields:
- **Bucket** -- the S3 bucket name.
- **Region** -- the AWS region (e.g. `us-east-1`). Leave empty for services that do not require it.
- **Access Key ID / Secret Access Key** -- IAM credentials with `s3:PutObject`, `s3:GetObject`, `s3:DeleteObject`, and `s3:ListBucket` on the target bucket.
- **Endpoint URL** -- optional. Set this for S3-compatible services (e.g. `https://s3.us-west-004.backblazeb2.com`). Leave empty for AWS S3.
- **Path prefix** -- optional folder prefix inside the bucket (e.g. `backups/`).

#### FTP / SFTP

Uploads archives to a remote FTP or SFTP server.

Configuration fields:
- **Host / Port** -- address of the FTP or SFTP server.
- **Username / Password** -- credentials for authentication.
- **Remote path** -- directory on the server where archives are stored.
- **Protocol** -- FTP or SFTP.

#### rclone

Uses rclone to transfer archives, giving access to over 70 cloud and on-premise storage providers. Rclone must be enabled in Settings, and you must provide a valid `rclone.conf` (either by pasting it in Settings or bind-mounting the config file).

Configuration fields:
- **Remote name** -- the name of the rclone remote as it appears in your `rclone.conf` (e.g. `myremote`).
- **Remote path** -- the path within the remote to store archives (e.g. `backups/`).

Use the "Test Connection" button on any storage backend to verify credentials before creating jobs.

### Retention policies

A retention policy defines rules for automatically deleting old backups. Policies are applied per job, after each successful backup completes. They can also be run manually from the Retention page.

The policy runs these steps in order:

1. Collect all successful backup records for the job, sorted newest first.
2. Always keep at least **Min Backups** records, regardless of age or count.
3. If **Max Backups** is set and the total exceeds it, delete the oldest records beyond the limit (while still respecting Min Backups).
4. Delete any remaining records older than **Retention Days** (while still respecting Min Backups).

When a record is deleted, the corresponding file is also deleted from the storage backend. If the storage deletion fails (e.g. network error), the database record is still removed and the failure is logged.

Policy fields:

| Field | Description |
|---|---|
| Retention Days | Records older than this many days are eligible for deletion. |
| Min Backups | The minimum number of successful backups to keep, regardless of age. |
| Max Backups | The maximum number of successful backups to keep. Optional. Set to 0 for no limit. |

### Notifications

Notification channels are configured independently of jobs. A channel can subscribe to any combination of success, warning, and failure events. The global settings (notify on success, notify on warning, notify on failure) act as toggles on top of per-channel event subscriptions.

#### Email (SMTP)

Sends a plain text email via SMTP.

Required fields:
- **SMTP Host / Port** -- the outgoing mail server.
- **From Address** -- the sender address.
- **To Addresses** -- comma-separated list of recipients.
- **Use TLS** -- whether to use STARTTLS (recommended).
- **Username / Password** -- SMTP credentials if the server requires authentication.

#### Slack

Sends a message to a Slack channel via an incoming webhook.

Required fields:
- **Webhook URL** -- the Slack incoming webhook URL.
- **Channel** -- optional. Overrides the default channel configured in the webhook.

#### Discord

Sends an embed message via a Discord webhook.

Required fields:
- **Webhook URL** -- the Discord webhook URL from your server's channel settings.
- **Username** -- optional display name for the webhook bot.
- **Avatar URL** -- optional avatar image URL for the webhook bot.

#### Gotify

Sends a push notification to a self-hosted Gotify server.

Required fields:
- **Server URL** -- base URL of your Gotify server (e.g. `https://gotify.example.com`).
- **App Token** -- the application token from the Gotify admin panel.
- **Priority** -- optional. Overrides the default priority (failure=8, warning=5, success=2).

#### ntfy

Sends a push notification via ntfy (cloud or self-hosted).

Required fields:
- **Server URL** -- defaults to `https://ntfy.sh`. Set to your own instance URL if self-hosted.
- **Topic** -- the ntfy topic to publish to.
- **Access Token** -- optional. Required if the topic requires authentication.

#### Generic webhook

Posts a JSON payload to any URL via HTTP POST.

Required fields:
- **URL** -- the endpoint to POST to.
- **Headers** -- optional JSON object of extra request headers (e.g. for auth tokens).

The payload structure:

```json
{
  "source": "dvbm",
  "event": "success",
  "job_name": "myapp",
  "message": "Backup completed: 142.3 MB",
  "timestamp": "2025-05-17T02:00:01.234567+00:00"
}
```

### Job queue and concurrency

`MAX_CONCURRENT_BACKUPS` (default: 1) controls how many jobs run at the same time. When a job is triggered and the limit is already reached, it enters a queue and waits until a slot opens.

The Job Queue page in the UI shows all jobs that are currently running or waiting in the queue. It polls every 3 seconds while jobs are active and every 5 seconds otherwise.

Jobs in the queue show as "In Queue" status. Jobs that have acquired a slot and are executing show as "Running".

Each job also has an optional `timeout_seconds` field. If the job runs longer than its timeout, it is marked as failed in the database and the queue slot is released. The underlying thread cannot be killed, so it will continue in the background until it finishes or the process exits, but it will no longer block other jobs.

### Restore

The Restore page lists all recorded successful backups. Selecting a backup and clicking Restore:

1. Downloads the archive from the storage backend to the staging directory.
2. Stops the containers associated with the job.
3. Extracts the archive and imports each volume directory back into the named Docker volume using a temporary helper container.
4. Restarts the containers.
5. Deletes the local copy of the archive.

If any volume import fails, the restore is marked as a warning and the other volumes are still imported. The containers are restarted regardless of partial failures.

Restore does not create a new backup record. It is a one-way operation with no built-in rollback.

### Config backup

The config backup automatically exports the app configuration to a `.zip` file and uploads it to a storage backend on a schedule. The zip file contains the same data as the manual export from Settings: all jobs, schedules, storage backends, retention policies, notification channels, and settings, in JSON format.

It is configured entirely in Settings:

- Enable it, choose a storage backend, and choose a schedule.
- Optionally assign a retention policy to limit how many config backups are kept.
- Optionally assign a notification channel to be alerted on success or failure.

You can also trigger a config backup immediately from Settings without waiting for the schedule.

The zip can be re-imported from Settings to restore a previous configuration. Importing merges by primary key, so existing records are updated and new records are added.

### Syslog forwarding

When syslog is enabled in Settings, the app connects to the configured syslog server on startup and forwards all log entries. The connection is UDP or TCP. The facility and priority are set based on the configured facility and the log level.

Changes to syslog settings take effect immediately on save, without a restart.

---

## API reference

All API routes require a `Bearer` token in the `Authorization` header. Get a token by calling `POST /api/auth/login`.

### Auth

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/auth/login` | Authenticate and receive a JWT token. Body: `{"password": "..."}`. |

### Jobs

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/jobs` | List all backup jobs with live status (matched containers, last run, queue state). |
| `GET` | `/api/jobs/{id}` | Get a single backup job. |
| `POST` | `/api/jobs` | Create a backup job. |
| `PUT` | `/api/jobs/{id}` | Update a backup job. |
| `DELETE` | `/api/jobs/{id}` | Delete a backup job. |
| `POST` | `/api/jobs/{id}/run` | Trigger a backup immediately. Returns immediately; the job runs in the background. |
| `POST` | `/api/jobs/{id}/pause` | Disable the job (stops it from running on schedule). |
| `POST` | `/api/jobs/{id}/resume` | Re-enable a paused job. |
| `GET` | `/api/jobs/{id}/stats` | Per-job stats: success rate (30d), total backups, average duration, recent records, and recent logs. |

### Schedules

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/schedules` | List all schedules. |
| `GET` | `/api/schedules/{id}` | Get a single schedule. |
| `POST` | `/api/schedules` | Create a schedule. |
| `PUT` | `/api/schedules/{id}` | Update a schedule. |
| `DELETE` | `/api/schedules/{id}` | Delete a schedule. |

### Storage Backends

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/storages` | List all storage backends. |
| `GET` | `/api/storages/{id}` | Get a single storage backend. |
| `POST` | `/api/storages` | Create a storage backend. |
| `PUT` | `/api/storages/{id}` | Update a storage backend. |
| `DELETE` | `/api/storages/{id}` | Delete a storage backend. |
| `POST` | `/api/storages/{id}/test` | Test the connection to a storage backend. |
| `GET` | `/api/storages/rclone/remotes` | List rclone remote names from the current rclone config. |

### Retention Policies

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/rotations` | List all retention policies. |
| `GET` | `/api/rotations/{id}` | Get a single retention policy. |
| `POST` | `/api/rotations` | Create a retention policy. |
| `PUT` | `/api/rotations/{id}` | Update a retention policy. |
| `DELETE` | `/api/rotations/{id}` | Delete a retention policy. |
| `POST` | `/api/rotations/{id}/run` | Apply a retention policy immediately across all jobs that use it. |

### Backups (records)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/backups` | List backup records. Supports `?job_id=`, `?status=`, `?limit=`, `?offset=` query params. |
| `GET` | `/api/backups/{id}` | Get a single backup record. |
| `POST` | `/api/backups/{id}/restore` | Trigger a restore from this backup record. Runs in the background. |
| `DELETE` | `/api/backups/{id}` | Delete a backup record (and its file from storage, if found). |
| `POST` | `/api/backups/import` | Register an existing archive file as a backup record without running a restore. |

### Notifications

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/notifications` | List all notification channels. |
| `GET` | `/api/notifications/{id}` | Get a single notification channel. |
| `POST` | `/api/notifications` | Create a notification channel. |
| `PUT` | `/api/notifications/{id}` | Update a notification channel. |
| `DELETE` | `/api/notifications/{id}` | Delete a notification channel. |
| `POST` | `/api/notifications/{id}/test` | Send a test notification through this channel. |

### Logs

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/logs` | List log entries. Supports `?level=`, `?job_name=`, `?limit=`, `?offset=` query params. |
| `DELETE` | `/api/logs` | Delete all log entries. |

### Dashboard

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/dashboard` | Returns aggregate stats: total jobs, recent backup count, success rate, storage used, recent activity. |

### Settings

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/settings` | Get all settings as a key-value object. |
| `PUT` | `/api/settings` | Update settings. Body: `{"settings": {"key": "value", ...}}`. |
| `POST` | `/api/settings/reset` | Reset all settings to defaults. |
| `GET` | `/api/settings/export` | Download all configuration as a `.zip` file. |
| `POST` | `/api/settings/import` | Upload a previously exported `.zip` to restore configuration. |
| `POST` | `/api/settings/config-backup/run` | Trigger a config backup immediately. |

---

## Data persistence

The `data` volume contains:
- `dvbm.db` -- the SQLite database. This holds all jobs, schedules, storage backends, retention policies, notification channels, backup records, logs, and settings.
- `certs/` -- the auto-generated TLS certificate and private key.

Back this volume up. Losing it means losing all configuration and backup history.

The `temp` volume is a staging area. Archives are written here during a backup and deleted after the upload. It does not need to persist across restarts.

---

## TLS / HTTPS

HTTPS is on by default. On first start, the app generates a self-signed certificate and stores it in `/data/certs/cert.pem` and `/data/certs/key.pem`. The certificate is reused across restarts as long as the `data` volume persists.

To stop the browser warning, either import `cert.pem` into your OS or browser trust store, or use your own certificate.

**Using your own certificate:**

```yaml
volumes:
  - /etc/letsencrypt/live/myhost.example.com:/certs:ro
environment:
  - SSL_CERT_FILE=/certs/fullchain.pem
  - SSL_KEY_FILE=/certs/privkey.pem
```

**Disabling TLS:**

```yaml
environment:
  - SSL_ENABLED=false
```

---

## Database encryption

Setting `DB_ENCRYPTION_KEY` encrypts the SQLite database on disk using AES-256 via SQLCipher. The app handles the encryption transparently -- no changes needed elsewhere.

If you set `DB_ENCRYPTION_KEY` when an existing plaintext database is already present, the app migrates it to encrypted format on startup. A copy of the original is saved as `dvbm.db.plaintext.bak`.

If you lose the key, the database cannot be recovered. There is no way to decrypt it without the original key.

Do not change the key after initial setup without a migration plan. The app will fail to open the database if the key does not match.

---

## Security

### Docker socket access

This app manages your containers, so it needs the Docker socket
(`/var/run/docker.sock`). **Mounting the Docker socket grants control of the
Docker daemon, which is equivalent to root on the host.** The container runs as
root so that socket access works consistently across hosts (the socket's group
ownership varies between distributions).

To reduce this exposure, put a **Docker socket proxy** in front of the daemon
and grant only the API calls this app uses (list/inspect/start/stop containers,
volume and image operations) instead of mounting the raw socket. For example
using [`tecnativa/docker-socket-proxy`](https://github.com/Tecnativa/docker-socket-proxy):

```yaml
services:
  docker-socket-proxy:
    image: tecnativa/docker-socket-proxy
    environment:
      - CONTAINERS=1
      - IMAGES=1
      - VOLUMES=1
      - POST=1          # required to start/stop containers
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    restart: unless-stopped

  docker-volume-backup-manager:
    # ...
    environment:
      - DOCKER_SOCKET=tcp://docker-socket-proxy:2375
    # and remove the direct - /var/run/docker.sock:/var/run/docker.sock mount
```

Keep the app on a trusted network and behind authentication regardless.

### Other hardening

- **`JWT_SECRET` is required** — the app refuses to start without a strong,
  unique value (a shared/default signing key would let anyone forge tokens).
- **Set a strong `APP_PASSWORD`** — leaving it unset or at a known default logs
  a loud warning; the UI is otherwise unprotected.
- Notification/webhook targets are restricted from reaching cloud metadata /
  link-local addresses; private LAN targets remain allowed.

---

## Built with

- **Backend:** Python 3.12, FastAPI, SQLAlchemy, APScheduler, SQLCipher
- **Frontend:** React 18, TypeScript, Vite, Tailwind CSS, shadcn/ui, TanStack Query
- **Database:** SQLite (optional AES-256 encryption via SQLCipher)

> **Disclaimer:** The UI for this project was built with the assistance of [Claude Code](https://claude.ai/code) by Anthropic. The backend logic, architecture decisions, and overall project direction were written and directed by the project author.
