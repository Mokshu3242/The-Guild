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


class AssignWorkerIn(BaseModel):
    worker_id: UUID
    match_reason: str = Field(default="", max_length=500)


def get_job_in_my_guild(session: Session, job_id: UUID, me: Member) -> Job:
    job = session.get(Job, job_id)
    if not job or job.guild_id != me.guild_id:
        raise HTTPException(404, "Job not found")
    return job


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
    return get_job_in_my_guild(session, job_id, me)


@router.post("/{job_id}/assign")
def assign_worker(
    job_id: UUID,
    body: AssignWorkerIn,
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    job = get_job_in_my_guild(session, job_id, me)
    if job.referrer_id != me.id and me.role != "admin":
        raise HTTPException(403, "Only the poster or an admin can assign")
    if job.status in ("paid", "disputed"):
        raise HTTPException(400, f"Can't reassign a job that is {job.status}")

    worker = session.get(Member, body.worker_id)
    if not worker or worker.guild_id != job.guild_id:
        raise HTTPException(404, "Worker not in this guild")

    job.worker_id = worker.id
    job.match_reason = body.match_reason
    job.status = "matched"
    session.add(job)
    session.commit()
    session.refresh(job)
    return job