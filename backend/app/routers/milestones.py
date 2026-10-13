from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.config import settings
from app.db import get_session
from app.deps import get_current_member
from app.models import AgentAction, Deposit, Invoice, Member, Milestone
from app.routers.jobs import get_job_in_my_guild
from app.services import deposits as deposits_svc

router = APIRouter(prefix="/jobs/{job_id}/milestones", tags=["milestones"])


class CreateMilestoneIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    scope: str = Field(default="", max_length=4000)
    amount_cents: int = Field(gt=0, le=10_000_000)  # max $100,000


@router.post("")
def create_milestone(
    job_id: UUID,
    body: CreateMilestoneIn,
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    job = get_job_in_my_guild(session, job_id, me)
    if job.referrer_id != me.id and me.role != "admin":
        raise HTTPException(403, "Only the poster or an admin can add milestones")

    milestone = Milestone(
        job_id=job.id,
        title=body.title,
        scope=body.scope,
        amount=body.amount_cents,
    )
    session.add(milestone)
    session.commit()
    session.refresh(milestone)
    return milestone


@router.get("")
def list_milestones(
    job_id: UUID,
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    get_job_in_my_guild(session, job_id, me)
    return session.exec(select(Milestone).where(Milestone.job_id == job_id)).all()


@router.delete("/{milestone_id}")
def delete_milestone(
    job_id: UUID,
    milestone_id: UUID,
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    job = get_job_in_my_guild(session, job_id, me)
    if job.referrer_id != me.id and me.role != "admin":
        raise HTTPException(403, "Only the poster or an admin can remove milestones")

    milestone = session.get(Milestone, milestone_id)
    if not milestone or milestone.job_id != job.id:
        raise HTTPException(404, "Milestone not found")

    invoiced = session.exec(select(Invoice).where(Invoice.milestone_id == milestone.id)).first()
    if invoiced or milestone.status != "pending":
        raise HTTPException(400, "This milestone has been invoiced, so it can't be removed")

    deposits = session.exec(select(Deposit).where(Deposit.milestone_id == milestone.id)).all()
    for d in deposits:
        if d.status in ("created", "authorized"):
            raise HTTPException(400, "This milestone has a deposit on hold. Release it before removing the milestone.")
        if d.status == "captured":
            raise HTTPException(400, "This milestone was paid from a deposit, so it can't be removed")

    # Only voided deposits are left. They moved no money, so clear them out.
    for d in deposits:
        session.delete(d)
    session.flush()

    session.add(AgentAction(
        guild_id=job.guild_id,
        action="milestone.removed",
        inputs={"job_id": str(job.id), "by": me.name},
        result={"title": milestone.title, "amount_cents": milestone.amount},
    ))
    session.delete(milestone)
    session.commit()
    return {"status": "removed"}


@router.post("/{milestone_id}/deposit")
def request_deposit(
    job_id: UUID,
    milestone_id: UUID,
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    job = get_job_in_my_guild(session, job_id, me)
    if job.referrer_id != me.id and me.role != "admin":
        raise HTTPException(403, "Only the poster or an admin can request a deposit")
    if not job.worker_id:
        raise HTTPException(400, "Assign a worker first")
    milestone = session.get(Milestone, milestone_id)
    if not milestone or milestone.job_id != job.id:
        raise HTTPException(404, "Milestone not found")
    if milestone.status != "pending":
        raise HTTPException(400, f"Can't hold a deposit on a milestone that is {milestone.status}")
    try:
        d = deposits_svc.create_deposit(session, job, milestone, me, settings.public_base_url)
    except ValueError as e:
        session.rollback()
        raise HTTPException(400, str(e))
    except httpx.HTTPStatusError as e:
        session.rollback()
        raise HTTPException(502, f"PayPal error: {e.response.text[:300]}")
    session.commit()
    session.refresh(d)
    return d