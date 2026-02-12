"""Backup Buddy – FastAPI application entry point."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
