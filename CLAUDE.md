# Docker Volume Backup Manager v3 (DVBM)

Self-hosted web app that backs up Docker container volumes. It runs as a single
container and is configured entirely through a browser UI.

## What it does (function)

- Matches containers to a **backup job** via a Docker label (`dvbm.job=<job name>`,
  key configurable).
- On a cron schedule or on demand: stops the matched containers, exports their
  named volumes (through throwaway Alpine helper containers, so no host
  filesystem access is needed), bundles them into a `.tar.gz`, uploads it to a
  storage backend, restarts the containers, and records the result.
- **Restore** a recorded backup back into the volumes.
- **Storage backends:** local filesystem, S3-compatible, FTP/SFTP, rclone remotes.
- **Retention policies** prune old backups (by age / minimum / maximum counts).
- **Notifications** on success/warning/failure: email, Slack, Discord, Gotify,
  ntfy, generic webhook.
- **Config backup / export / import** (zip), optional **syslog** forwarding, plus
  a dashboard and logs view.

## Design / architecture

- **Backend:** Python 3.12, FastAPI + SQLAlchemy 2.0, APScheduler for cron.
  Launched by `start.py`, which auto-generates a self-signed TLS certificate
  (unless one is supplied) and then runs uvicorn.
- **Frontend:** React 18 + TypeScript + Vite + Tailwind + shadcn/ui + TanStack
  Query. Built to static assets and served by FastAPI as an SPA (same origin —
  no separate frontend server).
- **Storage:** SQLite in `/data` (WAL mode). Optional at-rest **AES-256
  encryption** via SQLCipher (`DB_ENCRYPTION_KEY`). Schema changes go through an
  append-only versioned migration registry in `app/database.py`.
- **Services** (`backend/app/services/`): `backup_service` (backup/restore
  orchestration), `docker_service` (Docker SDK + helper containers),
  `storage_service` (per-backend handlers), `scheduler_service` (APScheduler),
  `rotation_service` (retention), `notification_service`, `config_backup_service`.
- **Routers** (`backend/app/routers/`): auth, dashboard, jobs, schedules,
  storages, rotations, backups, logs, notifications, settings.
- **Execution model:** each backup/restore runs in a **killable `spawn`
  subprocess** so a hung or timed-out job can be force-terminated; a semaphore
  (`MAX_CONCURRENT_BACKUPS`, default 1) serializes jobs to avoid concurrent
  container/volume conflicts.
- **Auth:** a single admin password (`APP_PASSWORD`) issues JWT bearer tokens
  signed with a required `JWT_SECRET`, with server-side revocation (a
  token-version claim; `POST /api/auth/logout` invalidates all outstanding
  tokens).
- **Container:** one image. Mounts: `/var/run/docker.sock` (to manage containers
  — note this is host-root-equivalent), `/data` (SQLite DB + TLS certs; persist
  this), `/backups` (temporary archive staging), and optionally `/local-backups`.

## Goals & scope

- **Primary goals:**
  1. **Security & data safety** — secure by default (TLS on, authentication
     required, optional at-rest encryption) and never lose or corrupt data:
     backup and migration operations are verified and atomic, keep a backup, and
     never mutate the original until a verified replacement exists.
  2. **Simple self-hosting** — a single container, minimal setup, with everything
     configured through the UI.
- Broad storage/notification compatibility and running entirely from inside a
  container (no host filesystem access) are supporting design choices in service
  of those goals.
- **Scope:** single-admin by design. Multi-user accounts and role-based access
  are **out of scope** — one shared admin credential is intentional.

## Tests

Two layers under `backend/tests/`:

- **`unit/`** — no Docker, no network: validation rules, secret masking, the
  rclone flag allowlist, SSRF blocking, login throttling, retention arithmetic.
  Sub-second.
- **`integration/`** — real Docker containers and volumes, plus a MinIO and an
  SFTP container, exercising backup and restore end to end against all four
  storage backends. The source volume is destroyed between backup and restore,
  so a test only passes if the archive genuinely contains the data.

```bash
cd backend && pytest tests/unit     # fast
cd backend && pytest tests          # everything (needs Docker)
```

Integration tests skip automatically when the Docker daemon is unreachable.
Everything they create is namespaced `dvbmtest-*` and removed in teardown.
`backend/tests/README.md` has the coverage table and notes for extending it.

**Changes to backup, restore or retention should come with a test.** These are
the paths where a silent failure means unrecoverable data loss, and several
past bugs (backups recorded as successful with an empty archive, retention
deleting a job's last backup, containers left stopped after a failure) were
invisible without one.

## Repository guidelines for AI tools

### Rules

- **Do not push to `main`.** Direct pushes to `main` by AI tools are prohibited.
  Develop on a feature branch and open a pull request; a human merges it.
- **Code changes are only approved for Opus or Fable models.** Other models must
  not modify code in this repository. (Non-code assistance — reading, explaining,
  reviewing — is fine on any model.)
