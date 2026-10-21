from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.db import get_session
from app.deps import get_current_member
from app.models import Job, Member
from app.services.evidence import build_evidence

router = APIRouter(prefix="/jobs", tags=["evidence"])


@router.get("/{job_id}/evidence")
def evidence(job_id: UUID, me: Member = Depends(get_current_member), session: Session = Depends(get_session)):
    """Read only. The poster, the worker, or an admin."""
    job = session.get(Job, job_id)
    if not job or job.guild_id != me.guild_id:
        raise HTTPException(404, "Job not found")
    if me.role != "admin" and me.id not in (job.referrer_id, job.worker_id):
        raise HTTPException(403, "Only the poster, the worker, or an admin can open the evidence pack")
    return build_evidence(session, job)
