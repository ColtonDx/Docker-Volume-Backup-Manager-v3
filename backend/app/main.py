"""Backup Buddy – FastAPI application entry point."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    scheduler_service.start()
    yield
    # Shutdown
    scheduler_service.shutdown()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# CORS – allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

# ---- Serve built frontend (production) -----------------------------------
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
if STATIC_DIR.is_dir():
    # Serve static assets (JS, CSS, images) normally
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="assets")

    # SPA catch-all: any non-API route returns index.html so client-side
    # routing works on page refresh / direct navigation.
    _index_html = STATIC_DIR / "index.html"

    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        # If a static file exists at the path, serve it (e.g. robots.txt, favicon)
        static_file = STATIC_DIR / full_path
        if full_path and static_file.is_file():
            return FileResponse(static_file)
        return FileResponse(_index_html)
