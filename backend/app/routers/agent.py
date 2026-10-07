from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from app.db import get_session
from app.deps import get_current_member
from app.models import AgentAction, Member

router = APIRouter(prefix="/agent", tags=["agent"])


@router.get("/actions")
def list_actions(
    limit: int = Query(default=50, ge=1, le=200),
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    return session.exec(
        select(AgentAction)
        .where(AgentAction.guild_id == me.guild_id)
        .order_by(AgentAction.created_at.desc())
        .limit(limit)
    ).all()