# Docker Volume Backup Manager v3

A self-hosted web app for automating Docker container volume backups. It stops your containers, archives their volumes, uploads the archive to your chosen storage backend, and restarts the containers. Runs as a single Docker container with a browser-based UI.

**Full documentation and source:** [github.com/ColtonDx/Docker-Volume-Backup-Manager-v3](https://github.com/ColtonDx/Docker-Volume-Backup-Manager-v3)

---

## What it does

- Backs up named Docker volumes by matching containers via a Docker label
- Schedules backups using standard cron expressions
- Stores archives on local disk, Amazon S3 / S3-compatible services, FTP/SFTP, or rclone (70+ providers)
- Applies retention policies to automatically clean up old backups by age, minimum count, or maximum count
- Sends notifications on success, warning, or failure via Email, Slack, Discord, Gotify, ntfy, or generic webhook
- Restores any recorded backup through the UI
- Optionally encrypts the database at rest with AES-256 (SQLCipher)

---

## Quick start

```yaml
services:
  docker-volume-backup-manager:
    image: coltondx/docker-volume-backup-manager-v3:latest
    container_name: docker-volume-backup-manager
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - data:/data
      - temp:/backups
      - ./local-backups:/local-backups
    environment:
      - APP_PASSWORD=changeme

volumes:
  data:
  temp:
```

Open the UI at `https://localhost:8000`. Accept the self-signed certificate warning on first visit, or import `/data/certs/cert.pem` into your browser or OS trust store.

---

## Labelling containers for backup

Add a Docker label to any container you want included in a backup job. The label value must match the job name set in the UI.

```yaml
services:
  myapp:
    image: myapp:latest
    labels:
      - "dvbm.job=myapp"
```

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `APP_PASSWORD` | `changeme` | Web UI login password. |
| `JWT_SECRET` | hardcoded default | Signs session tokens. Set a long random string in production. |
| `JWT_EXPIRE_HOURS` | `24` | Session length in hours. |
| `APP_NAME` | `Docker Volume Backup Manager` | Display name shown in the sidebar. |
| `DOCKER_LABEL_KEY` | `dvbm.job` | Docker label key used to match containers to jobs. |
| `TZ` | `UTC` | Timezone for cron schedule evaluation. Must be a valid IANA name. |
| `MAX_CONCURRENT_BACKUPS` | `1` | Number of backup jobs that can run at the same time. |
| `JOB_TIMEOUT_SECONDS` | `7200` | Max runtime per job before it is marked failed. Set to 0 to disable. |
| `DB_ENCRYPTION_KEY` | unset | Enables AES-256 database encryption. Do not lose this key. |
| `ALLOWED_HOSTS` | `*` | Comma-separated Host header allowlist. |
| `ALLOWED_ORIGINS` | `*` | Comma-separated CORS origin allowlist. |
| `SSL_ENABLED` | `true` | Set to `false` to serve over plain HTTP. |
| `SSL_CERT_FILE` | auto | Path to a custom TLS certificate. |
| `SSL_KEY_FILE` | auto | Path to the corresponding private key. |

---

## Storage backends

| Backend | Notes |
|---|---|
| Local filesystem | Bind-mount a host directory to make backups persist. |
| Amazon S3 / S3-compatible | Works with MinIO, Backblaze B2, Cloudflare R2, and others. |
| FTP / SFTP | Username/password authentication. |
| rclone | Enable rclone in Settings and paste your `rclone.conf`. Supports 70+ providers. |

---

> **Disclaimer:** The UI for this project was built with the assistance of [Claude Code](https://claude.ai/code) by Anthropic.
