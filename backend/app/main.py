"""Backup Buddy – FastAPI application entry point."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import settings
from app.database import init_db

# Router imports
from app.routers import (
    auth,
    backups,
    dashboard,
    jobs,
    logs,
    notifications,
    rotations,
    schedules,
    settings as settings_router,
    storages,
)
from app.services.scheduler_service import scheduler_service


def _configure_syslog_on_startup() -> None:
    """Read syslog settings from DB and attach handler if enabled."""
    import json
    import logging
    _log = logging.getLogger(__name__)
    try:
        from app.database import SessionLocal
        from app.models import Setting
        from app.syslog_handler import configure_syslog
        db = SessionLocal()
        try:
            syslog_keys = ("syslog_enabled", "syslog_host", "syslog_port",
                           "syslog_protocol", "syslog_facility")
            syslog_settings: dict = {}
            for key in syslog_keys:
                row = db.get(Setting, key)
                if row and row.value is not None:
                    try:
                        syslog_settings[key] = json.loads(row.value)
                    except (json.JSONDecodeError, TypeError):
                        syslog_settings[key] = row.value
            if syslog_settings:
                configure_syslog(syslog_settings)
        finally:
            db.close()
    except Exception as exc:
        _log.warning("Could not configure syslog on startup: %s", exc)


def _configure_timezone_on_startup() -> None:
    """Read the 'timezone' DB setting and apply it before the scheduler starts."""
    import json
    import logging
    _log = logging.getLogger(__name__)
    try:
        from app.database import SessionLocal
        from app.models import Setting
        db = SessionLocal()
        try:
            row = db.get(Setting, "timezone")
            if row and row.value:
                try:
                    tz = json.loads(row.value)
                except (json.JSONDecodeError, TypeError):
                    tz = row.value
                if isinstance(tz, str) and tz.strip():
                    from app.services.scheduler_service import scheduler_service
                    settings.TIMEZONE = scheduler_service._normalise_tz(tz)
                    _log.info("Timezone loaded from DB: %s", settings.TIMEZONE)
        finally:
            db.close()
    except Exception as exc:
        _log.warning("Could not load timezone from DB on startup: %s", exc)


def _sync_rclone_config_on_startup() -> None:
    """Ensure the rclone config file is written to disk from DB settings."""
    import json
    import logging
    _log = logging.getLogger(__name__)
    try:
        from app.database import SessionLocal
        from app.models import Setting
        db = SessionLocal()
        try:
            config_text = None
            for key in ("rclone_config_inline", "rclone_config_text"):
                row = db.get(Setting, key)
                if row and row.value:
                    val = json.loads(row.value) if row.value.startswith('"') else row.value
                    if isinstance(val, str) and val.strip():
                        config_text = val.strip()
                        break
            if config_text:
                config_path = Path(settings.RCLONE_CONFIG)
                config_path.parent.mkdir(parents=True, exist_ok=True)
                config_path.write_text(config_text + "\n")
                _log.info("Rclone config synced to %s on startup", config_path)
        finally:
            db.close()
    except Exception as exc:
        _log.warning("Could not sync rclone config on startup: %s", exc)


def _recover_interrupted_jobs() -> None:
    """Clean up jobs that were running when the process last stopped.

    A record left in "running" is otherwise reported as an active job forever,
    and the containers it stopped are never restarted.
    """
    import json, logging
    _log = logging.getLogger(__name__)
    try:
        from datetime import datetime, timezone

        from app.database import SessionLocal
        from app.models import BackupRecord, LogEntry
        from app.services.docker_service import docker_service

        db = SessionLocal()
        try:
            stale = db.query(BackupRecord).filter(BackupRecord.status == "running").all()
            if not stale:
                return

            for record in stale:
                record.status = "error"
                record.error_message = "Interrupted by application restart"
                record.completed_at = datetime.now(timezone.utc)

                job_name = record.job.name if record.job else "unknown"
                try:
                    names = json.loads(record.containers_stopped or "[]")
                except (json.JSONDecodeError, TypeError):
                    names = []

                if names:
                    try:
                        by_name = {c["name"]: c["id"] for c in docker_service.list_containers(all=True)}
                        ids = [by_name[n] for n in names if n in by_name]
                        started = docker_service.start_containers(ids)
                        _log.info(
                            "Restarted %d container(s) left stopped by interrupted job '%s'",
                            len(started), job_name,
                        )
                    except Exception as exc:
                        _log.error("Could not restart containers for '%s': %s", job_name, exc)

                db.add(LogEntry(
                    level="warning",
                    job_name=job_name,
                    message="Job was interrupted by an application restart",
                    details=(
                        f"Containers restored: {', '.join(names)}" if names
                        else "No containers were recorded as stopped"
                    ),
                ))

            db.commit()
            _log.warning("Marked %d interrupted job(s) as failed on startup", len(stale))
        finally:
            db.close()
    except Exception as exc:
        _log.warning("Interrupted-job recovery failed: %s", exc)


def _sweep_backup_temp_dir() -> None:
    """Remove archives left behind by an interrupted or failed run."""
    import logging, shutil
    _log = logging.getLogger(__name__)
    try:
        temp_dir = settings.BACKUP_TEMP_DIR
        if not temp_dir.is_dir():
            return
        removed = 0
        for entry in temp_dir.iterdir():
            if entry.name.startswith("bb_") and entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
                removed += 1
            elif entry.suffix == ".gz" and entry.is_file():
                try:
                    entry.unlink()
                    removed += 1
                except OSError as exc:
                    _log.warning("Could not remove stale temp file %s: %s", entry, exc)
        if removed:
            _log.info("Swept %d stale item(s) from %s", removed, temp_dir)
    except Exception as exc:
        _log.warning("Temp directory sweep failed: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    # Defense in depth: enforce secret validation even if the app is launched
    # directly via `uvicorn app.main:app` instead of start.py.
    settings.validate_secrets()
    init_db()
    _recover_interrupted_jobs()
    _sweep_backup_temp_dir()
    _configure_timezone_on_startup()
    _sync_rclone_config_on_startup()
    _configure_syslog_on_startup()
    scheduler_service.start()
    yield
    # Shutdown
    scheduler_service.shutdown()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# CORS – origins from ALLOWED_ORIGINS env var (default: "*" for dev).
# allow_credentials is False: auth is a bearer token in the Authorization
# header, not a cookie, so credentialed cross-origin requests aren't needed.
# This also avoids the invalid/insecure "*" + credentials combination.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Trusted hosts – added after CORS so it runs first (outermost middleware layer).
# Requests whose Host header is not in the allowlist are rejected with 400
# before reaching CORS or any route handler.
# Only active when ALLOWED_HOSTS is set to something other than "*".
if settings.allowed_hosts_list != ["*"]:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.allowed_hosts_list,
    )

# ---- API routers ---------------------------------------------------------
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
app.include_router(schedules.router, prefix="/api/schedules", tags=["schedules"])
app.include_router(storages.router, prefix="/api/storages", tags=["storages"])
app.include_router(rotations.router, prefix="/api/rotations", tags=["rotations"])
app.include_router(backups.router, prefix="/api/backups", tags=["backups"])
app.include_router(logs.router, prefix="/api/logs", tags=["logs"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["notifications"])
app.include_router(settings_router.router, prefix="/api/settings", tags=["settings"])


# ---- Health check (unauthenticated) --------------------------------------
# Registered before the SPA catch-all so orchestrators/HEALTHCHECK can probe it.
@app.get("/health", tags=["health"])
@app.get("/api/health", tags=["health"])
def health():
    """Liveness/readiness probe: DB reachable and scheduler running.

    A static 200 cannot distinguish a working app from one whose scheduler
    thread has died or whose database is unreachable, so both are checked.
    """
    from sqlalchemy import text as _text

    from app.database import SessionLocal

    db_ok = False
    try:
        db = SessionLocal()
        try:
            db.execute(_text("SELECT 1"))
            db_ok = True
        finally:
            db.close()
    except Exception:
        db_ok = False

    scheduler_ok = bool(
        scheduler_service._scheduler and scheduler_service._scheduler.running
    )
    healthy = db_ok and scheduler_ok
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={
            "status": "ok" if healthy else "degraded",
            "database": "ok" if db_ok else "error",
            "scheduler": "running" if scheduler_ok else "stopped",
            "version": settings.APP_VERSION,
        },
    )


# ---- Serve built frontend (production) -----------------------------------
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def safe_static_file(root: Path, full_path: str) -> Path | None:
    """Resolve *full_path* under *root*, returning the file only if it is a real
    file contained inside *root*.

    Prevents path traversal: a raw request such as "GET /../secret" would
    otherwise escape the static directory and read arbitrary container files.
    Returns None when the path is empty, escapes the root, or is not a file.
    """
    if not full_path:
        return None
    candidate = (root / full_path).resolve()
    if candidate.is_relative_to(root) and candidate.is_file():
        return candidate
    return None


if STATIC_DIR.is_dir():
    # Resolved absolute root used to contain every served path. Symlinks and
    # ".." segments are collapsed by resolve() so containment can be checked.
    _static_root = STATIC_DIR.resolve()

    # Serve static assets (JS, CSS, images) normally
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")

    # SPA catch-all: any non-API route returns index.html so client-side
    # routing works on page refresh / direct navigation.
    _index_html = STATIC_DIR / "index.html"

    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        # Serve a real static file (e.g. robots.txt, favicon) only if it stays
        # inside the static root; otherwise fall back to the SPA entry point.
        static_file = safe_static_file(_static_root, full_path)
        if static_file is not None:
            return FileResponse(static_file)
        return FileResponse(_index_html)
