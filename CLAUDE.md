# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Docker Volume Backup Manager v3 is a full-stack web app for managing Docker container volume backups. It features scheduled backups, multiple storage backends (local, S3, FTP/SFTP, rclone), retention policies, and notifications (email, Slack, Discord, Gotify, ntfy, webhooks).

The app runs as a single Docker container: a multi-stage build produces a React frontend (served as static files) and a Python FastAPI backend, all accessible on one port.

## Commands

### Frontend Development
```bash
npm install          # Install dependencies
npm run dev          # Vite dev server on :8080, proxies /api to localhost:8000
npm run build        # Production build to dist/
npm run lint         # ESLint
npm test             # Run Vitest once
npm run test:watch   # Vitest in watch mode
```

### Docker (full stack)
```bash
docker-compose up    # Build and run full app on localhost:8000
docker-compose down  # Stop containers
```

The backend must be running separately when using `npm run dev` — it expects FastAPI at `localhost:8000`.

## Architecture

### Request Flow
```
Browser → React (TanStack Query) → /api/* → FastAPI routers → services → Docker/DB/Storage
```

All frontend routes are served as SPA via a FastAPI catch-all. API endpoints are prefixed `/api/`.

### Backend (`backend/app/`)
- **`main.py`** — FastAPI app init, middleware, SPA catch-all, lifespan hooks (starts APScheduler)
- **`config.py`** — All settings; can be overridden via env vars or the settings page in the UI
- **`models.py`** / **`schemas.py`** / **`database.py`** — SQLAlchemy ORM (SQLite), Pydantic schemas, migration-on-startup
- **`auth.py`** — Single-user JWT auth; password set via `APP_PASSWORD` env var

#### Services (`backend/app/services/`)
| Service | Role |
|---|---|
| `backup_service.py` | Orchestrates full backup: stop containers → tar volumes → upload → restart → record |
| `docker_service.py` | Docker SDK wrapper: list/inspect containers, export/import volumes |
| `storage_service.py` | Unified upload/download/delete across localfs, S3, FTP, rclone |
| `scheduler_service.py` | APScheduler wrapper syncing DB schedules to cron jobs |
| `rotation_service.py` | Retention policy enforcement (age/min/max backups) |
| `notification_service.py` | Async notifications on backup events |

#### Routers (`backend/app/routers/`)
One router per feature area: `auth`, `jobs`, `schedules`, `storages`, `rotations`, `backups`, `dashboard`, `logs`, `notifications`, `settings`.

### Frontend (`src/`)
- **`api/`** — TypeScript fetch client (`client.ts`), typed API functions (`index.ts`), TS interfaces (`types.ts`)
- **`pages/`** — One file per page: Dashboard, BackupJobs, JobDetail, Schedules, Storages, Rotations, Notifications, Logs, Restore, Settings
- **`contexts/`** — `AuthContext` (JWT token in sessionStorage), `ColorThemeContext` (dark/light/cyberpunk), `AutoRefreshContext`
- **`components/`** — shadcn-ui wrappers (Radix UI + Tailwind) plus layout/navbar

### Database Schema
Key tables: `backup_jobs`, `backup_records`, `storage_backends`, `schedules`, `retention_policies`, `notification_channels`, `log_entries`, `settings` (key-value).

Schema migrations run automatically on backend startup via `database.py`.

## Key Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `APP_PASSWORD` | `"admin"` | Web UI login password |
| `JWT_SECRET` | hardcoded default | JWT signing key |
| `DOCKER_LABEL_KEY` | `"dvbm.job"` | Container label used to match backup jobs |
| `DATA_DIR` | `/data` | SQLite DB location |
| `BACKUP_TEMP_DIR` | `/tmp/dvbm` | Staging dir for archives |
| `RCLONE_BINARY` | `/usr/bin/rclone` | rclone executable |
| `TZ` | `UTC` | Timezone for cron schedules |

## Container Label Convention

Containers are matched to backup jobs via a Docker label. The label key defaults to `dvbm.job` and is set in `config.py` / `DOCKER_LABEL_KEY`. The label value on the container should match the job name.
