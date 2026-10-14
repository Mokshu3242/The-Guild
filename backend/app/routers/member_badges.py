from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.db import get_session
from app.deps import get_current_member
from app.models import Member
from app.services.trust_badges import badges_for, summarize

router = APIRouter(prefix="/members", tags=["members"])


def _member_in_my_guild(session: Session, member_id: UUID, me: Member) -> Member:
    m = session.get(Member, member_id)
    if not m or m.guild_id != me.guild_id:
        raise HTTPException(404, "Member not found")
    return m


@router.get("/{member_id}/badges")
def member_badges(
    member_id: UUID,
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    m = _member_in_my_guild(session, member_id, me)
    return {"member_id": str(m.id), "badges": badges_for(session, m)}


@router.post("/{member_id}/reputation")
def member_reputation(
    member_id: UUID,
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    m = _member_in_my_guild(session, member_id, me)
    result = summarize(session, m, by=me)
    session.commit()
    return result