from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import LogEntry
from app.schemas import LogEntryOut

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("", response_model=List[LogEntryOut])
def list_logs(
    level: str | None = Query(None),
    job_name: str | None = Query(None),
    search: str | None = Query(None),
    limit: int = Query(200, le=1000),
    offset: int = Query(0),
    db: Session = Depends(get_db),
):
    q = db.query(LogEntry).order_by(LogEntry.created_at.desc())
    if level:
        q = q.filter(LogEntry.level == level)
    if job_name:
        q = q.filter(LogEntry.job_name == job_name)
    if search:
        pattern = f"%{search}%"
        q = q.filter(
            LogEntry.message.ilike(pattern) | LogEntry.job_name.ilike(pattern)
        )
    return q.offset(offset).limit(limit).all()


@router.delete("", status_code=204)
def clear_logs(
    level: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Clear logs, optionally filtered by level."""
    q = db.query(LogEntry)
    if level:
        q = q.filter(LogEntry.level == level)
    q.delete(synchronize_session=False)
    db.commit()
