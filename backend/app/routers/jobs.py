from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.services.ai import AIError
from app.services.matcher import match_job
from app.db import get_session
from app.deps import get_current_member

from app.models import AgentAction, Job, Member, Milestone
from app.services.scope_builder import MilestoneDraft, build_scope

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

class MatchIn(BaseModel):
    auto_assign: bool = False


@router.post("/{job_id}/match")
def match(
    job_id: UUID,
    body: MatchIn,
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    job = get_job_in_my_guild(session, job_id, me)
    if job.referrer_id != me.id and me.role != "admin":
        raise HTTPException(403, "Only the poster or an admin can match")
    if job.status not in ("open", "matched"):
        raise HTTPException(400, f"Can't match a job that is {job.status}")

    try:
        pick = match_job(session, job)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except AIError as e:
        session.rollback()
        raise HTTPException(502, f"AI matching failed: {e}")

    if body.auto_assign:
        job.worker_id = UUID(pick["top_member_id"])
        job.match_reason = pick["reason"]
        job.status = "matched"
        session.add(job)

    session.commit()
    return {**pick, "assigned": body.auto_assign}

class ScopeBriefIn(BaseModel):
    brief: str = Field(min_length=30, max_length=4000)


class ApplyScopeIn(BaseModel):
    milestones: list[MilestoneDraft] = Field(min_length=1, max_length=6)


def _can_edit_scope(job: Job, me: Member) -> None:
    if job.referrer_id != me.id and me.role != "admin":
        raise HTTPException(403, "Only the poster or an admin can set milestones")
    if job.status not in ("open", "matched"):
        raise HTTPException(400, f"Can't change milestones on a job that is {job.status}")


@router.post("/{job_id}/scope/draft")
def draft_scope(
    job_id: UUID,
    body: ScopeBriefIn,
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    job = get_job_in_my_guild(session, job_id, me)
    _can_edit_scope(job, me)
    try:
        draft = build_scope(session, job, me, body.brief)
    except AIError as e:
        session.rollback()
        raise HTTPException(502, f"The AI couldn't draft milestones: {e}")
    session.commit()
    return draft


@router.post("/{job_id}/scope/apply")
def apply_scope(
    job_id: UUID,
    body: ApplyScopeIn,
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    job = get_job_in_my_guild(session, job_id, me)
    _can_edit_scope(job, me)
    if session.exec(select(Milestone).where(Milestone.job_id == job.id)).first():
        raise HTTPException(400, "This job already has milestones. Add more one at a time below.")

    created = [
        Milestone(job_id=job.id, title=m.title.strip(), scope=m.scope.strip(), amount=m.amount_cents)
        for m in body.milestones
    ]
    session.add_all(created)
    session.add(AgentAction(
        guild_id=job.guild_id,
        action="scope.applied",
        inputs={"job_id": str(job.id), "count": len(created), "by": me.name},
        result={"titles": [m.title for m in created], "total_cents": sum(m.amount for m in created)},
    ))
    session.commit()
    for m in created:
        session.refresh(m)
    return {"created": len(created), "milestones": created}