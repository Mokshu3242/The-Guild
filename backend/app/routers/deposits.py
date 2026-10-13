from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.db import get_session
from app.deps import get_current_member, require_admin
from app.models import Deposit, Job, Member, Milestone
from app.services import deposits as svc
from app.services.ai import AIError

router = APIRouter(prefix="/deposits", tags=["deposits"])


class DeliveryIn(BaseModel):
    note: str = Field(min_length=15, max_length=2000)


def _pp_error(e: httpx.HTTPStatusError) -> HTTPException:
    return HTTPException(502, f"PayPal error: {e.response.text[:300]}")


def _mine(session: Session, deposit_id: UUID, me: Member) -> Deposit:
    d = session.get(Deposit, deposit_id)
    if not d or d.guild_id != me.guild_id:
        raise HTTPException(404, "Deposit not found")
    return d


# ---- Fixed paths first ----

@router.get("/return", response_class=HTMLResponse, include_in_schema=False)
def deposit_return(cancelled: int = 0):
    msg = ("You cancelled. Nothing was held or charged." if cancelled else
           "Thanks! The amount is now on hold. You won't be charged until the work is accepted. You can close this tab.")
    return f"<html><body style='font-family:sans-serif;padding:40px'><h2>The Guild</h2><p>{msg}</p></body></html>"


@router.get("/for-job/{job_id}")
def deposits_for_job(job_id: UUID, me: Member = Depends(get_current_member),
                     session: Session = Depends(get_session)):
    job = session.get(Job, job_id)
    if not job or job.guild_id != me.guild_id:
        raise HTTPException(404, "Job not found")
    return session.exec(
        select(Deposit).join(Milestone, Deposit.milestone_id == Milestone.id)
        .where(Milestone.job_id == job_id).order_by(Deposit.created_at.desc())
    ).all()


# ---- Per-deposit actions ----

@router.post("/{deposit_id}/refresh")
def refresh(deposit_id: UUID, me: Member = Depends(get_current_member),
            session: Session = Depends(get_session)):
    _mine(session, deposit_id, me)
    try:
        result = svc.refresh_and_authorize(session, deposit_id)
    except httpx.HTTPStatusError as e:
        session.rollback()
        raise _pp_error(e)
    session.commit()
    return result


@router.post("/{deposit_id}/review")
def review(deposit_id: UUID, body: DeliveryIn, admin: Member = Depends(require_admin),
           session: Session = Depends(get_session)):
    _mine(session, deposit_id, admin)
    try:
        verdict = svc.review_delivery(session, deposit_id, admin, body.note)
    except AIError as e:
        session.rollback()
        raise HTTPException(502, f"The AI couldn't check the delivery: {e}")
    session.commit()
    return verdict


@router.post("/{deposit_id}/capture")
def capture(deposit_id: UUID, admin: Member = Depends(require_admin),
            session: Session = Depends(get_session)):
    _mine(session, deposit_id, admin)
    try:
        result = svc.capture_deposit(session, deposit_id, admin)
    except ValueError as e:
        session.rollback()
        raise HTTPException(400, str(e))
    except httpx.HTTPStatusError as e:
        session.rollback()
        raise _pp_error(e)
    session.commit()
    return result


@router.post("/{deposit_id}/void")
def void(deposit_id: UUID, admin: Member = Depends(require_admin),
         session: Session = Depends(get_session)):
    _mine(session, deposit_id, admin)
    try:
        result = svc.void_deposit(session, deposit_id, admin)
    except httpx.HTTPStatusError as e:
        session.rollback()
        raise _pp_error(e)
    session.commit()
    return result