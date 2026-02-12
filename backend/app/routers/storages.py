import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import StorageBackend
from app.schemas import StorageBackendCreate, StorageBackendOut, StorageBackendUpdate

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("", response_model=List[StorageBackendOut])
def list_storages(db: Session = Depends(get_db)):
    return db.query(StorageBackend).all()


@router.get("/{storage_id}", response_model=StorageBackendOut)
def get_storage(storage_id: int, db: Session = Depends(get_db)):
    storage = db.query(StorageBackend).get(storage_id)
    if not storage:
        raise HTTPException(status_code=404, detail="Storage backend not found")
    return storage


@router.post("", response_model=StorageBackendOut, status_code=201)
def create_storage(body: StorageBackendCreate, db: Session = Depends(get_db)):
    storage = StorageBackend(
        name=body.name,
        type=body.type,
        config_json=json.dumps(body.config),
    )
    db.add(storage)
    db.commit()
    db.refresh(storage)
    return storage


@router.put("/{storage_id}", response_model=StorageBackendOut)
def update_storage(storage_id: int, body: StorageBackendUpdate, db: Session = Depends(get_db)):
    storage = db.query(StorageBackend).get(storage_id)
    if not storage:
        raise HTTPException(status_code=404, detail="Storage backend not found")
    if body.name is not None:
        storage.name = body.name
    if body.type is not None:
        storage.type = body.type
    if body.config is not None:
        storage.config_json = json.dumps(body.config)
    db.commit()
    db.refresh(storage)
    return storage


@router.delete("/{storage_id}", status_code=204)
def delete_storage(storage_id: int, db: Session = Depends(get_db)):
    storage = db.query(StorageBackend).get(storage_id)
    if not storage:
        raise HTTPException(status_code=404, detail="Storage backend not found")
    db.delete(storage)
    db.commit()


@router.post("/{storage_id}/test")
def test_storage_connection(storage_id: int, db: Session = Depends(get_db)):
    """Test connectivity to the storage backend."""
    storage = db.query(StorageBackend).get(storage_id)
    if not storage:
        raise HTTPException(status_code=404, detail="Storage backend not found")

    from app.services.storage_service import storage_service
    config = json.loads(storage.config_json or "{}")
    ok, msg = storage_service.test_connection(storage.type, config)
    if not ok:
        return {"success": False, "message": msg}
    return {"success": True, "message": msg}
