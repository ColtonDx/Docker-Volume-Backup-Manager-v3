import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import NotificationChannel
from app.schemas import (
    NotificationChannelCreate,
    NotificationChannelOut,
    NotificationChannelUpdate,
)

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("", response_model=List[NotificationChannelOut])
def list_notifications(db: Session = Depends(get_db)):
    return db.query(NotificationChannel).all()


@router.get("/{channel_id}", response_model=NotificationChannelOut)
def get_notification(channel_id: int, db: Session = Depends(get_db)):
    channel = db.query(NotificationChannel).get(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Notification channel not found")
    return channel


@router.post("", response_model=NotificationChannelOut, status_code=201)
def create_notification(body: NotificationChannelCreate, db: Session = Depends(get_db)):
    channel = NotificationChannel(
        name=body.name,
        type=body.type,
        config_json=json.dumps(body.config),
        events_json=json.dumps(body.events),
        enabled=body.enabled,
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


@router.put("/{channel_id}", response_model=NotificationChannelOut)
def update_notification(
    channel_id: int, body: NotificationChannelUpdate, db: Session = Depends(get_db)
):
    channel = db.query(NotificationChannel).get(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Notification channel not found")
    if body.name is not None:
        channel.name = body.name
    if body.type is not None:
        channel.type = body.type
    if body.config is not None:
        channel.config_json = json.dumps(body.config)
    if body.events is not None:
        channel.events_json = json.dumps(body.events)
    if body.enabled is not None:
        channel.enabled = body.enabled
    db.commit()
    db.refresh(channel)
    return channel


@router.delete("/{channel_id}", status_code=204)
def delete_notification(channel_id: int, db: Session = Depends(get_db)):
    channel = db.query(NotificationChannel).get(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Notification channel not found")
    db.delete(channel)
    db.commit()


@router.post("/{channel_id}/test")
def test_notification(channel_id: int, db: Session = Depends(get_db)):
    """Send a test notification."""
    channel = db.query(NotificationChannel).get(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Notification channel not found")

    from app.services.notification_service import notification_service
    config = json.loads(channel.config_json or "{}")
    ok, msg = notification_service.send_test(channel.type, config)
    return {"success": ok, "message": msg}
