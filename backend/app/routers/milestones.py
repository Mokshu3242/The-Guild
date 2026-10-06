from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.db import get_session
from app.deps import get_current_member
from app.models import Member, Milestone
from app.routers.jobs import get_job_in_my_guild

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