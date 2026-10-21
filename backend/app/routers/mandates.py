from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.db import get_session
from app.deps import get_current_member, require_admin
from app.models import Member
from app.services import mandates

router = APIRouter(prefix="/mandates", tags=["mandates"])


class MandateIn(BaseModel):
    active: bool | None = None
    remind_max_tier: int | None = Field(default=None, ge=0, le=3)
    auto_claim: bool | None = None
    claim_max_cents: int | None = Field(default=None, ge=0, le=100_000)       # $1,000 hard ceiling
    claim_min_confidence: int | None = Field(default=None, ge=50, le=100)
    auto_advance: bool | None = None
    advance_max_cents: int | None = Field(default=None, ge=0, le=100_000)


@router.get("")
def get_mandate(me: Member = Depends(get_current_member), session: Session = Depends(get_session)):
    """Every member can see what the agent may do on its own. Only admins change it."""
    return mandates.out(session, mandates.get(session, me.guild_id))


@router.put("")
def save_mandate(body: MandateIn, admin: Member = Depends(require_admin), session: Session = Depends(get_session)):
    m = mandates.save(session, admin, body.model_dump(exclude_unset=True))
    session.commit()
    session.refresh(m)
    return mandates.out(session, m)
