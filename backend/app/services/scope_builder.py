from pydantic import BaseModel, Field
from sqlmodel import Session

from app.models import AgentAction, Job, Member
from app.services.ai import run_ai_json
from app.prompts import SCOPE_DRAFT as SYSTEM

MAX_MILESTONE_CENTS = 10_000_000  # $100,000, same cap as manual milestones


class MilestoneDraft(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    scope: str = Field(min_length=10, max_length=600)
    amount_cents: int = Field(ge=100, le=MAX_MILESTONE_CENTS)


class ScopeDraft(BaseModel):
    summary: str = Field(min_length=10, max_length=400)
    budget_cents: int | None = Field(default=None, ge=0)
    pricing_basis: str = Field(max_length=200)
    milestones: list[MilestoneDraft] = Field(min_length=1, max_length=6)

def build_scope(session: Session, job: Job, me: Member, brief: str) -> ScopeDraft:
    worker = session.get(Member, job.worker_id) if job.worker_id else None
    rate = f"${worker.hourly_rate_cents // 100}/hr ({worker.name})" if worker and worker.hourly_rate_cents else "not set, assume $80/hr"

    prompt = (
        f"Client: {job.client_name}\n"
        f"Job on file: {job.description}\n"
        f"Worker's hourly rate: {rate}\n\n"
        f"Client brief:\n{brief.strip()}"
    )
    draft = run_ai_json(
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        feature="scope",
        schema=ScopeDraft, temperature=0.2, max_tokens=900,
    )

    session.add(AgentAction(
        guild_id=job.guild_id,
        action="scope.drafted",
        inputs={"job_id": str(job.id), "brief_len": len(brief)},
        result={
            "summary": draft.summary,
            "milestone_count": len(draft.milestones),
            "total_cents": sum(m.amount_cents for m in draft.milestones),
            "budget_cents": draft.budget_cents,
            "pricing_basis": draft.pricing_basis,
        },
    ))
    return draft