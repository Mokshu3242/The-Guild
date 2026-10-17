from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.db import get_session
from app.deps import get_current_member
from app.models import AgentAction, Deposit, Invoice, Job, Member, Milestone, ScopeFlag
from app.services.ai import AIError
from app.services.client_risk import assess_client
from app.services.matcher import match_job
from app.services.scope_builder import MilestoneDraft, build_scope
from app.services.scope_creep import check_creep
from app.services.skill_gap import assess_gap

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

class CheckMessageIn(BaseModel):
    message: str = Field(min_length=15, max_length=4000)


class AddonIn(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    amount_cents: int | None = Field(default=None, ge=100, le=10_000_000)


def _open_flag(session: Session, job: Job, flag_id: UUID) -> ScopeFlag:
    flag = session.exec(select(ScopeFlag).where(ScopeFlag.id == flag_id).with_for_update()).first()
    if not flag or flag.job_id != job.id:
        raise HTTPException(404, "Flag not found")
    if flag.status != "flagged":
        raise HTTPException(400, f"This flag was already {flag.status}")
    return flag


@router.post("/{job_id}/scope/check")
def check_message(
    job_id: UUID,
    body: CheckMessageIn,
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    job = get_job_in_my_guild(session, job_id, me)
    if me.id not in (job.referrer_id, job.worker_id) and me.role != "admin":
        raise HTTPException(403, "Only the poster, the worker, or an admin can check a message")
    if job.status not in ("open", "matched", "in_progress"):
        raise HTTPException(400, f"Can't check messages on a job that is {job.status}")
    try:
        flag = check_creep(session, job, me, body.message)
    except AIError as e:
        session.rollback()
        raise HTTPException(502, f"The AI couldn't review the message: {e}")
    session.commit()
    session.refresh(flag)
    return flag


@router.get("/{job_id}/scope/flags")
def list_flags(
    job_id: UUID,
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    get_job_in_my_guild(session, job_id, me)
    return session.exec(
        select(ScopeFlag).where(ScopeFlag.job_id == job_id).order_by(ScopeFlag.created_at.desc())
    ).all()


@router.post("/{job_id}/scope/flags/{flag_id}/add")
def add_from_flag(
    job_id: UUID,
    flag_id: UUID,
    body: AddonIn,
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    job = get_job_in_my_guild(session, job_id, me)
    if job.referrer_id != me.id and me.role != "admin":
        raise HTTPException(403, "Only the poster or an admin can add an add-on")
    if job.status not in ("open", "matched", "in_progress"):
        raise HTTPException(400, f"Can't add work to a job that is {job.status}")
    flag = _open_flag(session, job, flag_id)

    milestone = Milestone(
        job_id=job.id,
        title=(body.title or flag.suggested_title).strip(),
        scope=flag.suggested_scope or "Add-on requested by the client",
        amount=body.amount_cents or flag.suggested_amount_cents,
    )
    session.add(milestone)
    session.flush()

    flag.status = "added"
    flag.addon_milestone_id = milestone.id
    session.add(flag)
    session.add(AgentAction(
        guild_id=job.guild_id,
        action="scope.addon_added",
        inputs={"job_id": str(job.id), "by": me.name,
                "edited": milestone.amount != flag.suggested_amount_cents or milestone.title != flag.suggested_title},
        result={"title": milestone.title, "amount_cents": milestone.amount,
                "ai_suggested_cents": flag.suggested_amount_cents},
    ))
    session.commit()
    session.refresh(milestone)
    return {"status": "added", "milestone": milestone}


@router.post("/{job_id}/scope/flags/{flag_id}/dismiss")
def dismiss_flag(
    job_id: UUID,
    flag_id: UUID,
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    job = get_job_in_my_guild(session, job_id, me)
    if job.referrer_id != me.id and me.role != "admin":
        raise HTTPException(403, "Only the poster or an admin can dismiss a flag")
    flag = _open_flag(session, job, flag_id)
    flag.status = "dismissed"
    session.add(flag)
    session.add(AgentAction(
        guild_id=job.guild_id,
        action="scope.flag_dismissed",
        inputs={"job_id": str(job.id), "by": me.name},
        result={"title": flag.suggested_title, "amount_cents": flag.suggested_amount_cents},
    ))
    session.commit()
    return {"status": "dismissed"}

@router.post("/{job_id}/risk")
def score_risk(
    job_id: UUID,
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    job = get_job_in_my_guild(session, job_id, me)
    if job.referrer_id != me.id and me.role != "admin":
        raise HTTPException(403, "Only the poster or an admin can score this client")
    try:
        result = assess_client(session, job, me)
    except AIError as e:
        session.rollback()
        raise HTTPException(502, f"The AI couldn't explain the score: {e}")
    session.commit()
    return result

@router.post("/{job_id}/skill-gap")
def check_skill_gap(
    job_id: UUID,
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    job = get_job_in_my_guild(session, job_id, me)
    if job.referrer_id != me.id and me.role != "admin":
        raise HTTPException(403, "Only the poster or an admin can check the skills")
    if job.status not in ("open", "matched"):
        raise HTTPException(400, f"Can't check skills on a job that is {job.status}")
    try:
        result = assess_gap(session, job, me)
    except ValueError as e:
        session.rollback()
        raise HTTPException(400, str(e))
    except AIError as e:
        session.rollback()
        raise HTTPException(502, f"The AI couldn't read the skills: {e}")
    session.commit()
    return result


@router.delete("/{job_id}")
def delete_job(
    job_id: UUID,
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    job = get_job_in_my_guild(session, job_id, me)
    if job.referrer_id != me.id and me.role != "admin":
        raise HTTPException(403, "Only the person who posted this job or an admin can delete it")

    milestones = session.exec(select(Milestone).where(Milestone.job_id == job.id)).all()
    ms_ids = [m.id for m in milestones]

    # Once PayPal or the pool has touched a job, keep it for the record.
    # Claims always sit on invoices, so the invoice check covers them too.
    if ms_ids:
        if session.exec(select(Invoice).where(Invoice.milestone_id.in_(ms_ids))).first():
            raise HTTPException(400, "This job has invoices, so it can't be deleted. It stays for the payment record.")
        if session.exec(select(Deposit).where(Deposit.milestone_id.in_(ms_ids))).first():
            raise HTTPException(400, "This job has a deposit hold on record, so it can't be deleted.")

    for f in session.exec(select(ScopeFlag).where(ScopeFlag.job_id == job.id)).all():
        session.delete(f)
    for m in milestones:
        session.delete(m)
    session.flush()

    session.add(AgentAction(
        guild_id=job.guild_id,
        action="job.removed",
        inputs={"by": me.name},
        result={"client": job.client_name, "milestones": len(milestones)},
    ))
    session.delete(job)
    session.commit()
    return {"status": "deleted"}