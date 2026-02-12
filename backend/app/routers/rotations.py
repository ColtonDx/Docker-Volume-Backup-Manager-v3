from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import RetentionPolicy, BackupJob
from app.schemas import RetentionPolicyCreate, RetentionPolicyOut, RetentionPolicyUpdate

router = APIRouter(dependencies=[Depends(get_current_user)])


def _to_out(policy: RetentionPolicy, db: Session) -> dict:
    job_count = db.query(BackupJob).filter(BackupJob.retention_id == policy.id).count()
    return {
        "id": policy.id,
        "name": policy.name,
        "description": policy.description,
        "retention_days": policy.retention_days,
        "min_backups": policy.min_backups,
        "max_backups": policy.max_backups,
        "job_count": job_count,
        "created_at": policy.created_at,
        "updated_at": policy.updated_at,
    }


@router.get("", response_model=List[RetentionPolicyOut])
def list_retention_policies(db: Session = Depends(get_db)):
    policies = db.query(RetentionPolicy).all()
    return [_to_out(p, db) for p in policies]


@router.get("/{policy_id}", response_model=RetentionPolicyOut)
def get_retention_policy(policy_id: int, db: Session = Depends(get_db)):
    policy = db.query(RetentionPolicy).get(policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Retention policy not found")
    return _to_out(policy, db)


@router.post("", response_model=RetentionPolicyOut, status_code=201)
def create_retention_policy(body: RetentionPolicyCreate, db: Session = Depends(get_db)):
    policy = RetentionPolicy(**body.model_dump())
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return _to_out(policy, db)


@router.put("/{policy_id}", response_model=RetentionPolicyOut)
def update_retention_policy(
    policy_id: int, body: RetentionPolicyUpdate, db: Session = Depends(get_db)
):
    policy = db.query(RetentionPolicy).get(policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Retention policy not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(policy, field, value)
    db.commit()
    db.refresh(policy)
    return _to_out(policy, db)


@router.delete("/{policy_id}", status_code=204)
def delete_retention_policy(policy_id: int, db: Session = Depends(get_db)):
    policy = db.query(RetentionPolicy).get(policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Retention policy not found")
    db.delete(policy)
    db.commit()


@router.post("/{policy_id}/run")
def run_cleanup(policy_id: int, db: Session = Depends(get_db)):
    """Manually trigger retention cleanup for a policy."""
    policy = db.query(RetentionPolicy).get(policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Retention policy not found")

    from app.services.rotation_service import rotation_service
    removed = rotation_service.apply_policy(policy_id)
    return {"message": f"Cleanup complete. Removed {removed} backup(s)."}
