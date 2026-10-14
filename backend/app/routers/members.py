from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlmodel import Session, select

from app.db import get_session
from app.deps import get_current_member
from app.models import Member, Payout
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
    for field, value in body.model_dump(exclude_unset=True).items():
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