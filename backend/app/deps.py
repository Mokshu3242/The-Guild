from uuid import UUID

from fastapi import Depends, HTTPException
from sqlmodel import Session, select

from app.auth import get_current_user
from app.db import get_session
from app.models import Member


def get_current_member(
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Member:
    member = session.exec(
        select(Member).where(Member.user_id == UUID(user["sub"]))
    ).first()
    if not member:
        raise HTTPException(404, "You are not in a guild yet")
    return member


def require_admin(member: Member = Depends(get_current_member)) -> Member:
    if member.role != "admin":
        raise HTTPException(403, "Admin only")
    return member