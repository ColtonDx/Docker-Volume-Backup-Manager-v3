# Code.md — How the codebase works

A guided tour of the repository structure and the role of every significant piece of code.

---

## The big picture

The application is a single Docker container that serves both the API and the frontend from port 8000.

```
Browser
  │  HTTPS (self-signed cert, auto-generated on first start)
  ▼
FastAPI (Python, Uvicorn)
  ├── /api/*         → API routes (JSON)
  └── everything else → React SPA (index.html)

FastAPI internally uses:
  ├── SQLite database   (/data/dvbm.db)
  ├── Docker socket     (/var/run/docker.sock)
  ├── APScheduler       (in-process cron runner)
  └── rclone binary     (/usr/bin/rclone, optional)
```

There is no separate database server, no message queue, and no external process manager — everything runs inside one Python process.

---

## Repository layout

```
Docker-Volume-Backup-Manager-v3/
│
├── backend/
│   ├── app/                  ← Python package (the API)
│   │   ├── main.py           ← FastAPI app, middleware, SPA serving
│   │   ├── config.py         ← All settings (env vars)
│   │   ├── auth.py           ← JWT creation and verification
│   │   ├── database.py       ← SQLAlchemy engine, migrations, SQLCipher
│   │   ├── models.py         ← ORM table definitions
│   │   ├── schemas.py        ← Pydantic request/response shapes
│   │   ├── syslog_handler.py ← Optional remote syslog integration
│   │   ├── routers/          ← One file per feature area (API endpoints)
│   │   └── services/         ← Business logic (backup, docker, storage, etc.)
│   ├── start.py              ← Entry point: generates TLS cert, starts uvicorn
│   └── requirements.txt      ← Python dependencies
│
├── src/                      ← React frontend (TypeScript)
│   ├── api/                  ← HTTP client and typed API functions
│   ├── pages/                ← One component per page
│   ├── components/           ← Reusable UI components
│   ├── contexts/             ← React Context providers
│   ├── hooks/                ← Custom React hooks
│   └── lib/                  ← Utility functions
│
├── public/                   ← Static assets (favicon, etc.)
├── Dockerfile                ← Multi-stage build (Node → Python)
├── docker-compose.yml        ← Local deployment configuration
├── package.json              ← Frontend dependencies and scripts
└── vite.config.ts            ← Frontend build and dev-server config
```

---

## Startup sequence

When the container starts, `backend/start.py` runs first (it is the Docker `CMD`):

1. Reads `SSL_ENABLED` from the environment.
2. If SSL is on and no certificate exists at `/data/certs/cert.pem`, generates a self-signed RSA-2048 cert using Python's `cryptography` library.
3. Calls `uvicorn.run("app.main:app", ...)` programmatically, passing cert/key paths if SSL is enabled.

Uvicorn loads `backend/app/main.py`, which triggers the FastAPI `lifespan` startup hook:

1. `init_db()` — creates any missing database tables; runs lightweight column-addition migrations.
2. `_sync_rclone_config_on_startup()` — if an rclone config was previously saved via the UI, writes it back to disk (the container filesystem is ephemeral).
3. `_configure_syslog_on_startup()` — attaches a syslog log handler if syslog was enabled in settings.
4. `scheduler_service.start()` — loads all enabled backup schedules from the database and registers them with APScheduler.

---

## Configuration (`backend/app/config.py`)

All settings are class attributes on a single `Settings` instance (`settings`). They are read from environment variables at import time, with sensible defaults. No `.env` file is involved — Docker Compose or your container runtime supplies the values.

Notable properties (computed, not direct env vars):
- `database_url` — builds the SQLAlchemy connection string from `DATA_DIR` / `DB_PATH`.
- `db_file_path` — the absolute filesystem path to the SQLite file.
- `allowed_hosts_list` / `allowed_origins_list` — parse the comma-separated env var strings into Python lists.
- `ssl_cert_path` / `ssl_key_path` — resolve to either the user-supplied paths or the auto-generated defaults under `SSL_CERT_DIR`.

---

## Database (`backend/app/database.py`)

Uses SQLAlchemy 2 with a synchronous SQLite engine. Key decisions:

**Plain mode** (no `DB_ENCRYPTION_KEY`): standard `create_engine("sqlite:///path")` — identical to a typical SQLAlchemy setup.

**Encrypted mode** (`DB_ENCRYPTION_KEY` is set): uses SQLCipher via the `sqlcipher3` Python package. SQLCipher is a version of SQLite with transparent AES-256 encryption. The connection is created through a `creator` callable so that `PRAGMA key` is the very first statement on every new connection. `NullPool` is used to ensure every session gets a fresh connection (and therefore always runs the key PRAGMA).

The passphrase is not sent directly to SQLCipher; it's SHA-256 hashed first to produce a fixed 32-byte hex key (`PRAGMA key = "x'hexdigest'"`). This avoids SQLCipher version differences in KDF defaults.

**Migration**: if an existing plaintext database is found when encrypted mode is first enabled, it is automatically migrated: the plaintext DB is read with Python's built-in `sqlite3`, the SQL dump is replayed into a new SQLCipher database, and the original is replaced atomically. The plaintext file is kept as `dvbm.db.plaintext.bak`.

---

## ORM models (`backend/app/models.py`)

Each class maps to one database table:

| Model | Table | Purpose |
|---|---|---|
| `StorageBackend` | `storage_backends` | A named storage destination (localfs, S3, FTP, rclone). Credentials/config stored as JSON in `config_json`. |
| `Schedule` | `schedules` | A named cron expression. Multiple jobs can share one schedule. |
| `RetentionPolicy` | `retention_policies` | Rules for how long to keep backups (days, min/max count). |
| `BackupJob` | `backup_jobs` | The core entity. References a storage, schedule, and retention policy. Matches containers via `label_key`/`label_value`. |
| `BackupRecord` | `backup_records` | One row per backup execution. Records status, size, duration, error messages, which containers were stopped, which volumes were archived. |
| `LogEntry` | `log_entries` | Application log messages written to the database for display in the UI Logs page. |
| `NotificationChannel` | `notification_channels` | A configured notification destination. Config stored as JSON in `config_json`; subscribed events in `events_json`. |
| `Setting` | `settings` | Key-value store for all UI-configurable settings (rclone config text, syslog settings, etc.). |

---

## API layer

### Entry point (`backend/app/main.py`)

Registers all routers under `/api/` and mounts the built React app as static files. Any request that is not an API call and does not match a static file returns `index.html`, which lets React Router handle client-side navigation on page refresh.

Middleware stack (outer → inner, i.e. execution order on incoming requests):
1. `TrustedHostMiddleware` — rejects requests with an unrecognised `Host` header (only active when `ALLOWED_HOSTS` is set to something specific).
2. `CORSMiddleware` — handles cross-origin requests using `ALLOWED_ORIGINS`.

### Routers (`backend/app/routers/`)

Each file handles one resource area. All routes require a valid JWT (`dependencies=[Depends(get_current_user)]`), except `auth.py`.

| Router file | Prefix | Responsibility |
|---|---|---|
| `auth.py` | `/api/auth` | `POST /login` — validates password, returns JWT. |
| `jobs.py` | `/api/jobs` | CRUD for backup jobs. `POST /{id}/run` triggers an immediate backup. `GET /{id}/stats` returns per-job dashboard data. Each job response is *enriched* with live data from Docker (matched containers) and the most recent backup record. |
| `schedules.py` | `/api/schedules` | CRUD for cron schedules. |
| `storages.py` | `/api/storages` | CRUD for storage backends. `POST /{id}/test` tests connectivity. `GET /rclone/remotes` lists configured rclone remotes. |
| `rotations.py` | `/api/rotations` | CRUD for retention policies. `POST /{id}/apply` runs cleanup immediately. |
| `backups.py` | `/api/backups` | List/get backup records. `POST /{id}/restore` triggers a restore. `DELETE /{id}` removes a record (and optionally the remote file). |
| `dashboard.py` | `/api/dashboard` | Aggregated stats for the home screen: job counts, success rates, recent activity, upcoming schedules. |
| `logs.py` | `/api/logs` | Query log entries with level/job filtering and pagination. |
| `notifications.py` | `/api/notifications` | CRUD for notification channels. |
| `settings.py` | `/api/settings` | Get/set all key-value settings. Saving triggers `_sync_rclone_config()` to write the rclone config file to disk. Supports export (ZIP download) and import. |

### Schemas (`backend/app/schemas.py`)

Pydantic models that define the shape of API request bodies and response JSON. The `Out` schemas (e.g. `StorageBackendOut`) include `model_validator` methods that handle the ORM-to-dict conversion, particularly unpacking the `config_json` / `events_json` string columns back into Python dicts/lists.

### Authentication (`backend/app/auth.py`)

Single-user model. `POST /api/auth/login` accepts a password and returns a JWT signed with `JWT_SECRET` using HS256. The token expires after `JWT_EXPIRE_HOURS` (default 24). Every other API route uses `get_current_user` as a FastAPI dependency, which decodes and validates the token from the `Authorization: Bearer` header.

---

## Services (`backend/app/services/`)

Services contain the actual business logic. They are plain Python classes with a single module-level instance (e.g. `backup_service = BackupService()`).

### `backup_service.py`

The most important service. Orchestrates the full backup lifecycle in a background thread (so the API response returns immediately):

1. Find containers matching the job's label.
2. Collect all distinct volumes from those containers.
3. Stop the running containers.
4. Export each volume into a temporary directory using a helper Docker container.
5. Create a `.tar.gz` archive of all volumes.
6. Upload the archive to the configured storage backend.
7. Restart the stopped containers.
8. Write a `BackupRecord` to the database with status, size, duration.
9. Send notifications.
10. Apply the retention policy (delete old backups).

Restore is the reverse: download the archive from storage, extract it, import each volume directory back into Docker, restart containers.

**Important:** if a backup fails after containers have been stopped, those containers are **not** automatically restarted. They must be restarted manually. This is noted in the error log.

### `docker_service.py`

Wraps the Docker SDK. Key operations:
- `find_containers_by_label(key, value)` — returns containers whose labels match.
- `get_container_volumes(container_id)` — returns volume names and mount points.
- `export_volume(volume_name, dest_dir)` — runs a temporary Alpine container that bind-mounts the volume and copies its contents to a staging directory.
- `import_volume(volume_name, src_dir)` — the reverse: runs a temporary container to copy staging data back into a volume.
- `stop_containers` / `start_containers` — stop/start by container ID.

### `storage_service.py`

A unified interface for all storage backends. Every method (`upload`, `download`, `delete_remote`, `test_connection`, `list_files`) dispatches to a backend-specific handler based on the `backend_type` string (`localfs`, `s3`, `ftp`, `rclone`). S3 uses `boto3`, FTP/SFTP uses `paramiko`, rclone calls the `rclone` binary via `subprocess`.

### `scheduler_service.py`

Wraps APScheduler. `sync_jobs()` is called whenever jobs, schedules, or their enabled state changes. It reads all enabled backup jobs from the database and reconciles them with APScheduler's job list — adding new ones, updating changed ones, removing deleted ones. Each scheduled job calls `backup_service.run_backup(job_id)`.

### `rotation_service.py`

Applies a `RetentionPolicy` to a job's backup records. For each job using the policy:
1. Fetches all `success` records ordered by date.
2. Keeps at least `min_backups` records regardless of age.
3. Deletes records older than `retention_days`, never going below `min_backups`.
4. Deletes the oldest records if total count exceeds `max_backups`.
5. For each deleted record, also deletes the file from the storage backend.

### `notification_service.py`

Sends notifications to all enabled channels that subscribe to a given event type (`success`, `warning`, `failure`). Each channel type (Slack, Discord, Email, Gotify, ntfy, webhook) has its own async send function. Email uses SMTP; all others use HTTP via `httpx`.

---

## Frontend (`src/`)

A React 18 single-page application built with Vite.

### Data fetching

All API calls go through `src/api/index.ts`, which exports typed functions (`getJobs()`, `createJob(body)`, etc.). Each function calls `src/api/client.ts`, a thin fetch wrapper that reads the JWT from `sessionStorage` and attaches it as a Bearer token.

TanStack React Query is used throughout the pages to cache responses, refetch on window focus, and manage loading/error states.

### State management

There is no global state store (no Redux, no Zustand). All server state goes through React Query. The only client-side state that persists is:
- **Auth token** — stored in `sessionStorage` via `AuthContext` (`src/contexts/AuthContext.tsx`). Cleared automatically when the browser tab closes.
- **Colour theme** — stored in `localStorage` via `ColorThemeContext` (`src/contexts/ColorThemeContext.tsx`). Supports light, dark, and a cyberpunk theme.
- **Auto-refresh toggle** — in `AutoRefreshContext`, controls whether React Query polls in the background.

### Pages

Each file in `src/pages/` is a full page. React Router maps URL paths to these components in `src/App.tsx`.

| Page | Route | Purpose |
|---|---|---|
| `Login` | `/login` | Password form. Stores JWT on success. |
| `Dashboard` | `/` | Overview stats, recent jobs, upcoming schedules. |
| `BackupJobs` | `/jobs` | List and manage backup jobs. |
| `JobDetail` | `/jobs/:id` | Per-job stats, backup history, logs. |
| `Schedules` | `/schedules` | Manage cron schedules. |
| `Storages` | `/storages` | Manage storage backends. |
| `Rotations` | `/rotations` | Manage retention policies. |
| `Notifications` | `/notifications` | Manage notification channels. |
| `Restore` | `/restore` | Browse and restore from past backups. |
| `Logs` | `/logs` | Filterable application log viewer. |
| `Settings` | `/settings` | All app-wide settings, rclone config, export/import. |

### Components

`src/components/` contains layout (sidebar, navbar), a theme toggle, and re-exports of shadcn/ui components. shadcn/ui is not a runtime dependency — it is a collection of copy-pasted Radix UI + Tailwind components that live directly in `src/components/ui/`.

---

## Build and deployment

**Development (frontend only):**
```bash
npm install
npm run dev        # Vite dev server on :8080, proxies /api to localhost:8000
```
The backend must be running separately at `localhost:8000`.

**Production (Docker):**
```bash
docker compose up --build
```
The Dockerfile is a two-stage build:
1. **Stage 1 (Node):** runs `npm run build`, producing a `dist/` directory.
2. **Stage 2 (Python):** installs Python dependencies, copies backend code, copies the `dist/` from Stage 1 into `/app/static/`. FastAPI serves these static files.

Everything ends up in one image. There is no nginx or separate static file server.

---

## Known limitations and things to be aware of

- **Containers are not auto-restarted on backup failure.** If a backup fails after the stop step, containers stay down. Check the Logs page and restart manually.
- **Single-user only.** There is one password for the entire application; there is no per-user access control.
- **SQLite is not suitable for concurrent writes at scale**, but for a single-container backup manager this is not a concern in practice.
- **The rclone config (if used) is stored in the database** as plaintext and written to disk at startup. Enabling `DB_ENCRYPTION_KEY` encrypts the database copy; the on-disk file at `/root/.config/rclone/rclone.conf` is not additionally encrypted (this is standard rclone behaviour).
- **Backup archives are staged locally** before upload. Ensure `BACKUP_TEMP_DIR` has enough space for your largest expected archive.
