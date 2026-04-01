# Docker Volume Backup Manager v3

A self-hosted web application for managing automated Docker container volume backups. Configure scheduled backups, choose where they're stored, set retention policies, and get notified — all from a browser-based UI running inside a single Docker container.

---

## What it does

- **Backs up Docker volumes** by matching containers via a Docker label, stopping them, archiving their volumes into a `.tar.gz`, uploading the archive to your chosen storage, then restarting the containers automatically.
- **Schedules backups** using standard cron expressions.
- **Supports multiple storage backends**: local filesystem, Amazon S3 (or any S3-compatible service), FTP/SFTP, and rclone (supporting 70+ cloud providers).
- **Applies retention policies**: automatically delete old backups by age, minimum/maximum count, or a combination.
- **Sends notifications** on backup success, warning, or failure via Email, Slack, Discord, Gotify, ntfy, or any generic webhook.
- **Restores from any recorded backup** through the UI.

---

## Quick start

```bash
# 1. Edit the required environment variable in docker-compose.yml
#    Set APP_PASSWORD to something other than "changeme"

# 2. Start the container
docker compose up -d

# 3. Open the UI
#    https://localhost:8000
#    Accept the self-signed certificate warning on first visit,
#    or import /data/certs/cert.pem into your OS/browser trust store.
```

---

## Labelling containers for backup

The manager matches containers to backup jobs using a Docker label. Add the label to any container you want backed up:

```yaml
# In your application's docker-compose.yml (not this one)
services:
  myapp:
    image: myapp:latest
    labels:
      - "dvbm.job=myapp"   # value must match the Job Name set in the UI
```

The label key (`dvbm.job`) can be changed via the `DOCKER_LABEL_KEY` environment variable.

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `APP_PASSWORD` | `changeme` | Web UI login password. |
| `JWT_SECRET` | *(insecure default)* | Signs session tokens. Set a long random string in production. |
| `DB_ENCRYPTION_KEY` | *(unset)* | Enables SQLCipher AES-256 encryption for the database at rest. **Store this key safely — losing it makes the database permanently unreadable.** |
| `ALLOWED_HOSTS` | `*` | Comma-separated `Host` header allowlist (e.g. `myhost.local,localhost`). Requests from other hosts are rejected with 400. |
| `ALLOWED_ORIGINS` | `*` | Comma-separated CORS origin allowlist (e.g. `https://myhost.local`). |
| `SSL_ENABLED` | `true` | Serves the app over HTTPS. A self-signed cert is auto-generated on first start in `/data/certs/`. |
| `SSL_CERT_FILE` | *(auto)* | Path to a custom TLS certificate (e.g. from Let's Encrypt). |
| `SSL_KEY_FILE` | *(auto)* | Path to the corresponding private key. |
| `DOCKER_LABEL_KEY` | `dvbm.job` | Docker label key used to match containers to jobs. |
| `DATA_DIR` | `/data` | Directory for the SQLite database (and auto-generated TLS certs). |
| `BACKUP_TEMP_DIR` | `/backups` | Staging directory for building archives before upload. |
| `TZ` | `UTC` | Timezone used when evaluating cron schedules. |
| `APP_NAME` | `Docker Volume Backup Manager` | Display name shown in the sidebar. |

---

## Using your own TLS certificate

Mount your certificate files and point the app at them:

```yaml
volumes:
  - /etc/letsencrypt/live/myhost.local:/certs:ro
environment:
  - SSL_CERT_FILE=/certs/fullchain.pem
  - SSL_KEY_FILE=/certs/privkey.pem
```

---

## Storage backends

| Backend | Requirements |
|---|---|
| **Local filesystem** | A directory path inside the container. Bind-mount a host directory to make it persistent. |
| **Amazon S3** | Bucket name, region, access key ID, and secret. Works with any S3-compatible service (MinIO, Backblaze B2, Cloudflare R2, etc.). |
| **FTP / SFTP** | Host, port, username, and password (or key for SFTP). |
| **rclone** | A configured rclone remote. Paste your `rclone.conf` into Settings → rclone Configuration, or mount the config file at the default path. |

---

## Data persistence

The `data` Docker volume holds:
- `dvbm.db` — the SQLite database (all jobs, schedules, records, settings)
- `certs/` — auto-generated TLS certificate and private key

The `temp` volume is a staging area used while building archives. It does not need to survive container restarts.

---

## Security notes

- **HTTPS is on by default.** The self-signed cert is stored in the persistent `data` volume and reused across restarts. Import `cert.pem` into your browser or OS trust store to eliminate the warning.
- **Set `DB_ENCRYPTION_KEY`** to encrypt the SQLite database on disk using AES-256 (SQLCipher). An existing plaintext database is automatically migrated on first start with the key set; a backup is kept at `dvbm.db.plaintext.bak`.
- **Set `ALLOWED_HOSTS`** if the app is not behind a reverse proxy, to prevent host header injection.
- **Change `JWT_SECRET`** from the default. It is used to sign session tokens — anyone who knows the default can forge a valid session.

---

## Built with

- **Backend:** Python 3.12, FastAPI, SQLAlchemy, APScheduler, SQLCipher
- **Frontend:** React 18, TypeScript, Vite, Tailwind CSS, shadcn/ui, TanStack Query
- **Database:** SQLite (optional AES-256 encryption via SQLCipher)

> This project was built with assistance from AI tools including [Claude Code](https://claude.ai/code) by Anthropic.
