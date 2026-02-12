from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Schedule, BackupJob
from app.schemas import ScheduleCreate, ScheduleOut, ScheduleUpdate

router = APIRouter(dependencies=[Depends(get_current_user)])


def _to_out(schedule: Schedule, db: Session) -> dict:
    job_count = db.query(BackupJob).filter(BackupJob.schedule_id == schedule.id).count()
    return {
        "id": schedule.id,
        "name": schedule.name,
        "cron": schedule.cron,
        "description": schedule.description,
        "enabled": schedule.enabled,
        "job_count": job_count,
        "created_at": schedule.created_at,
        "updated_at": schedule.updated_at,
    }


@router.get("", response_model=List[ScheduleOut])
def list_schedules(db: Session = Depends(get_db)):
    schedules = db.query(Schedule).all()
    return [_to_out(s, db) for s in schedules]


@router.get("/{schedule_id}", response_model=ScheduleOut)
def get_schedule(schedule_id: int, db: Session = Depends(get_db)):
    schedule = db.query(Schedule).get(schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return _to_out(schedule, db)


@router.post("", response_model=ScheduleOut, status_code=201)
def create_schedule(body: ScheduleCreate, db: Session = Depends(get_db)):
    schedule = Schedule(**body.model_dump())
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return _to_out(schedule, db)


@router.put("/{schedule_id}", response_model=ScheduleOut)
def update_schedule(schedule_id: int, body: ScheduleUpdate, db: Session = Depends(get_db)):
    schedule = db.query(Schedule).get(schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(schedule, field, value)
    db.commit()
    db.refresh(schedule)
    return _to_out(schedule, db)


@router.delete("/{schedule_id}", status_code=204)
def delete_schedule(schedule_id: int, db: Session = Depends(get_db)):
    schedule = db.query(Schedule).get(schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    db.delete(schedule)
    db.commit()
