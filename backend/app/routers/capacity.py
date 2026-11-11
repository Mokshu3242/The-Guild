from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.db import get_session
from app.deps import get_current_member
from app.models import Member
from app.services.capacity import guild_capacity

router = APIRouter(prefix="/capacity", tags=["capacity"])


@router.get("")
def capacity(
    weeks: int = Query(default=2, ge=1, le=4),
    past: int = Query(default=0, ge=0, le=8),
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """14B. Who is busy until when, estimated from open milestones, plus `past` weeks of delivered work.
    Everyone in the guild can see it."""
    return guild_capacity(session, me.guild_id, weeks, past)
