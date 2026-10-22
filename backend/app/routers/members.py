from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlmodel import Session, select

from app.db import get_session
from app.deps import get_current_member
from app.models import Member, Payout
from app.services.notices import active_broadcasts, active_maintenance, upcoming_maintenance
from app.services.rate_advisor import advise

router = APIRouter(prefix="/me", tags=["members"])


class UpdateMeIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    paypal_email: str | None = None
    skills: list[str] | None = None
    hourly_rate_cents: int | None = Field(default=None, ge=0)
    available: bool | None = None
    # Empty string removes the photo.
    avatar_url: str | None = Field(default=None, max_length=500)
    # 14B: "YYYY-MM-DD" = busy until that day. Empty string clears it.
    available_from: str | None = Field(default=None, max_length=40)

    @field_validator("avatar_url")
    @classmethod
    def https_only(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if v and not v.startswith("https://"):
            raise ValueError("Photo link must start with https://")
        return v


@router.get("")
def get_me(me: Member = Depends(get_current_member)):
    return me


@router.patch("")
def update_me(
    body: UpdateMeIn,
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    data = body.model_dump(exclude_unset=True)
    if "available_from" in data:
        raw = (data.pop("available_from") or "").strip()
        if raw:
            try:
                day = datetime.fromisoformat(raw[:10]).replace(tzinfo=timezone.utc)
            except ValueError:
                raise HTTPException(400, "Use a date like 2026-11-05")
            me.available_from = day
        elif raw == "" and body.available_from is not None:
            me.available_from = None
    for field, value in data.items():
        if value is None:
            continue  # never wipe a field by sending null
        setattr(me, field, value)
    session.add(me)
    session.commit()
    session.refresh(me)
    return me


@router.get("/earnings")
def my_earnings(
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    payouts = session.exec(
        select(Payout).where(Payout.member_id == me.id).order_by(Payout.created_at.desc())
    ).all()
    return {"total_cents": sum(p.amount for p in payouts), "payouts": payouts}


@router.post("/rate-advice")
def rate_advice(
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    result = advise(session, me)
    session.commit()
    return result


@router.get("/notices")
def my_notices(
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Banners for this member's guild. Always allowed, even during maintenance."""
    m = active_maintenance(session, me.guild_id)
    soon = None if m else upcoming_maintenance(session, me.guild_id)
    return {
        "broadcasts": [
            {"id": str(b.id), "level": b.level, "title": b.title, "body": b.body}
            for b in active_broadcasts(session, me.guild_id)
        ],
        "maintenance": (
            {"id": str(m.id), "mode": m.mode, "message": m.message,
             "ends_at": m.ends_at.isoformat() if m.ends_at else None}
            if m else None
        ),
        "upcoming": (
            {"id": str(soon.id), "mode": soon.mode, "message": soon.message,
             "starts_at": soon.starts_at.isoformat()}
            if soon else None
        ),
    }

