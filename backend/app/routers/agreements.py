from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.db import get_session
from app.deps import get_current_member
from app.models import Member
from app.services import agreements as agree

router = APIRouter(prefix="/me", tags=["agreements"])


class PledgeIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    hash: str = Field(min_length=64, max_length=64)
    agree: bool


@router.get("/pledge")
def my_pledge(me: Member = Depends(get_current_member), session: Session = Depends(get_session)):
    return agree.pledge_state(session, me)


@router.post("/pledge")
def sign_my_pledge(
    body: PledgeIn,
    request: Request,
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    if not body.agree:
        raise HTTPException(400, "Tick the box to confirm you've read the pledge")
    agree.sign_pledge(session, me, body.name, body.hash, request)
    session.commit()
    return agree.pledge_state(session, me)
