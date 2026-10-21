from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.db import get_session
from app.deps import get_current_member
from app.models import AgentAction, Agreement, Job, Member, Milestone, utcnow
from app.services import agreements as agree
from app.services import portal as svc

# Public: no login. The token in the URL is the credential.
router = APIRouter(prefix="/portal", tags=["portal"])

# Members: manage the link and mark work delivered.
member_router = APIRouter(prefix="/jobs", tags=["portal"])


class ChangesIn(BaseModel):
    feedback: str = Field(min_length=15, max_length=1500)


class DeliveredIn(BaseModel):
    note: str = Field(default="", max_length=1500)


class AcceptIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    hash: str = Field(min_length=64, max_length=64)   # the exact text the client saw
    agree: bool


# ---------------- Client ----------------

@router.get("/{token}")
def view(token: str, background: BackgroundTasks, session: Session = Depends(get_session)):
    job = svc.job_by_token(session, token)
    data = svc.portal_view(session, job)
    a = data["agreement"]
    # Write the AI summary once, after the page has loaded. The rules summary shows meanwhile.
    if a["needs_signature"] and a["summary_by"] == "rules":
        background.add_task(agree.write_summary_in_background, job.id)
    return data


@router.post("/{token}/agreement")
def accept_agreement(token: str, body: AcceptIn, request: Request, session: Session = Depends(get_session)):
    job = svc.job_by_token(session, token)
    svc.block_writes_if_paused(session, job)
    if not body.agree:
        raise HTTPException(400, "Tick the box to confirm you've read the agreement")
    agree.accept_work(session, job, body.name, body.hash, request)
    session.commit()
    return svc.portal_view(session, job)


@router.post("/{token}/milestones/{milestone_id}/approve")
def approve(token: str, milestone_id: UUID, session: Session = Depends(get_session)):
    job = svc.job_by_token(session, token)
    svc.block_writes_if_paused(session, job)
    svc.client_approve(session, job, milestone_id)
    session.commit()
    return svc.portal_view(session, job)


@router.post("/{token}/milestones/{milestone_id}/changes")
def request_changes(
    token: str,
    milestone_id: UUID,
    body: ChangesIn,
    background: BackgroundTasks,
    session: Session = Depends(get_session),
):
    job = svc.job_by_token(session, token)
    svc.block_writes_if_paused(session, job)
    svc.client_request_changes(session, job, milestone_id, body.feedback)
    session.commit()
    background.add_task(svc.scope_check_in_background, job.id, body.feedback.strip())
    return svc.portal_view(session, job)


# ---------------- Members ----------------

def _job(session: Session, job_id: UUID, me: Member) -> Job:
    job = session.get(Job, job_id)
    if not job or job.guild_id != me.guild_id:
        raise HTTPException(404, "Job not found")
    return job


def _manage(session: Session, job_id: UUID, me: Member) -> Job:
    job = _job(session, job_id, me)
    if not svc.can_manage(job, me):
        raise HTTPException(403, "Only the poster, the worker or an admin can manage the client link")
    return job


def _log(session: Session, job: Job, action: str, me: Member) -> None:
    session.add(AgentAction(guild_id=job.guild_id, action=action,
                            inputs={"job_id": str(job.id), "by": me.name}, result={"client": job.client_name}))


@member_router.get("/{job_id}/portal")
def portal_status(job_id: UUID, me: Member = Depends(get_current_member), session: Session = Depends(get_session)):
    return svc.member_view(session, _job(session, job_id, me), me)


@member_router.post("/{job_id}/portal/enable")
def enable(job_id: UUID, me: Member = Depends(get_current_member), session: Session = Depends(get_session)):
    job = _manage(session, job_id, me)
    if not job.portal_token:
        svc.ensure_token(job)
        session.add(job)
        _log(session, job, "portal.enabled", me)
        session.commit()
    return svc.member_view(session, job, me)


@member_router.post("/{job_id}/portal/rotate")
def rotate(job_id: UUID, me: Member = Depends(get_current_member), session: Session = Depends(get_session)):
    job = _manage(session, job_id, me)
    job.portal_token = svc.new_token()
    job.portal_token_created_at = utcnow()
    session.add(job)
    _log(session, job, "portal.rotated", me)
    session.commit()
    return svc.member_view(session, job, me)


@member_router.delete("/{job_id}/portal")
def disable(job_id: UUID, me: Member = Depends(get_current_member), session: Session = Depends(get_session)):
    job = _manage(session, job_id, me)
    job.portal_token = None
    job.portal_token_created_at = None
    session.add(job)
    _log(session, job, "portal.disabled", me)
    session.commit()
    return svc.member_view(session, job, me)


@member_router.post("/{job_id}/milestones/{milestone_id}/delivered")
def delivered(
    job_id: UUID,
    milestone_id: UUID,
    body: DeliveredIn,
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    job = _job(session, job_id, me)
    if me.role != "admin" and me.id != job.worker_id:
        raise HTTPException(403, "Only the worker or an admin can mark work as delivered")
    m = session.get(Milestone, milestone_id)
    if not m or m.job_id != job.id:
        raise HTTPException(404, "Milestone not found")
    svc.mark_delivered(session, job, m, me, body.note)
    session.commit()
    return svc.member_view(session, job, me)


@member_router.get("/{job_id}/agreement")
def job_agreement(job_id: UUID, me: Member = Depends(get_current_member), session: Session = Depends(get_session)):
    """The current agreement text and every accepted version, for members of this guild."""
    job = _job(session, job_id, me)
    state = agree.work_state(session, job)
    state.pop("signed_ids", None)
    rows = session.exec(
        select(Agreement)
        .where(Agreement.job_id == job.id, Agreement.kind.in_(["work", "amendment"]))
        .order_by(Agreement.accepted_at)
    ).all()
    state["accepted"] = [
        {
            "kind": r.kind,
            "signer": r.signer_name,
            "email": r.signer_email,
            "accepted_at": r.accepted_at.isoformat(),
            "hash": r.sha256,
            "body": r.body,
        }
        for r in rows
    ]
    return state

