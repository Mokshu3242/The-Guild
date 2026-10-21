from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.db import get_session
from app.deps import require_admin
from app.models import ApiKey, Job, Member
from app.services import api_keys

router = APIRouter(prefix="/api-keys", tags=["api keys"])


class NewKeyIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)


@router.get("")
def list_keys(admin: Member = Depends(require_admin), session: Session = Depends(get_session)):
    keys = session.exec(select(ApiKey).where(ApiKey.guild_id == admin.guild_id).order_by(ApiKey.created_at.desc())).all()
    hires = {}
    for j in session.exec(select(Job).where(Job.guild_id == admin.guild_id, Job.source == "api")).all():
        hires[j.api_key_id] = hires.get(j.api_key_id, 0) + 1
    return [{**api_keys.row(k), "hires": hires.get(k.id, 0)} for k in keys]


@router.post("")
def create_key(body: NewKeyIn, admin: Member = Depends(require_admin), session: Session = Depends(get_session)):
    key, raw = api_keys.create(session, admin, body.name)
    session.commit()
    return {**api_keys.row(key), "hires": 0, "key": raw}


@router.delete("/{key_id}")
def revoke_key(key_id: UUID, admin: Member = Depends(require_admin), session: Session = Depends(get_session)):
    key = session.get(ApiKey, key_id)
    if not key or key.guild_id != admin.guild_id:
        raise HTTPException(404, "Key not found")
    if not key.active:
        return {"status": "revoked"}
    api_keys.revoke(session, key, admin)
    session.commit()
    return {"status": "revoked"}
