from uuid import UUID

from fastapi import Depends, HTTPException
from sqlmodel import Session, select

from app.auth import get_current_user
from app.config import settings
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


def _platform_emails() -> set[str]:
    return {e.strip().lower() for e in settings.platform_admins.split(",") if e.strip()}


def get_platform_admin(user: dict = Depends(get_current_user)) -> dict:
    """Platform admins are listed by email in PLATFORM_ADMINS.

    Checked from the signed login token, so it works even for someone who
    isn't a member of any guild. Nothing in the app can grant this.
    """
    allowed = _platform_emails()
    email = (user.get("email") or "").strip().lower()
    if not allowed or email not in allowed:
        # Same answer whether it's off or you're not on the list, so nobody learns which.
        raise HTTPException(403, "Not allowed")
    return {"email": email, "sub": user.get("sub")}