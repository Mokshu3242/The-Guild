from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.db import get_session
from app.deps import get_current_member
from app.models import Job, Member

router = APIRouter(prefix="/jobs", tags=["jobs"])


class CreateJobIn(BaseModel):
    client_name: str = Field(min_length=1, max_length=120)
    client_email: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=10, max_length=4000)


@router.post("")
def create_job(
    body: CreateJobIn,
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    job = Job(
        guild_id=me.guild_id,
        referrer_id=me.id,
        client_name=body.client_name,
        client_email=body.client_email,
        description=body.description,
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


@router.get("")
def list_jobs(
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    return session.exec(
        select(Job).where(Job.guild_id == me.guild_id).order_by(Job.created_at.desc())
    ).all()


@router.get("/{job_id}")
def get_job(
    job_id: UUID,
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    job = session.get(Job, job_id)
    if not job or job.guild_id != me.guild_id:
        raise HTTPException(404, "Job not found")
    return job