from typing import Literal

from pydantic import BaseModel, Field, model_validator
from sqlmodel import Session, select

from app.models import AgentAction, Job, Member, Milestone, ScopeFlag
from app.services.ai import run_ai_json
from app.services.scope_builder import MAX_MILESTONE_CENTS
from app.prompts import SCOPE_CREEP as SYSTEM

DEFAULT_RATE_CENTS = 8000  # $80/hr when the worker hasn't set a rate


class CreepDraft(BaseModel):
    verdict: Literal["in_scope", "out_of_scope", "unclear"]
    reason: str = Field(min_length=10, max_length=400)
    suggested_title: str = Field(default="", max_length=80)
    suggested_scope: str = Field(default="", max_length=600)
    estimated_hours: float = Field(default=0, ge=0, le=400)

    @model_validator(mode="after")
    def addon_needs_details(self):
        if self.verdict == "out_of_scope":
            if len(self.suggested_title.strip()) < 3 or self.estimated_hours < 0.5:
                raise ValueError("out_of_scope needs a suggested_title and estimated_hours of at least 0.5")
        return self

def _price_from_hours(hours: float, rate_cents: int) -> int:
    """Hours times rate, rounded to the nearest $5, within the milestone limits."""
    raw = round(hours * rate_cents)
    rounded = round(raw / 500) * 500
    return min(max(rounded, 100), MAX_MILESTONE_CENTS)


def check_creep(session: Session, job: Job, me: Member, message: str) -> ScopeFlag:
    milestones = session.exec(select(Milestone).where(Milestone.job_id == job.id)).all()

    worker = session.get(Member, job.worker_id) if job.worker_id else None
    has_rate = bool(worker and worker.hourly_rate_cents)
    rate_cents = worker.hourly_rate_cents if has_rate else DEFAULT_RATE_CENTS
    rate_label = f"${rate_cents // 100}/hr" + (f" ({worker.name})" if has_rate else ", the guild default")

    agreed = "\n".join(
        f"- {m.title}: {m.scope or '(no scope written)'} (${m.amount // 100})" for m in milestones
    ) or "(no milestones yet, so treat the job description as the agreed scope)"

    prompt = (
        f"Job: {job.description}\nWorker's hourly rate: {rate_label}\n\n"
        f"Agreed milestones:\n{agreed}\n\nClient's new message:\n{message.strip()}"
    )
    draft = run_ai_json(
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        feature="scope",
        schema=CreepDraft, temperature=0.2, max_tokens=600,
    )

    out = draft.verdict == "out_of_scope"
    amount = 0
    scope_text = ""
    if out:
        # The AI estimates hours. The code does the money math.
        amount = _price_from_hours(draft.estimated_hours, rate_cents)
        hours = f"{draft.estimated_hours:g}"
        scope_text = f"{draft.suggested_scope.strip()} About {hours} hours at {rate_label}.".strip()

    flag = ScopeFlag(
        guild_id=job.guild_id,
        job_id=job.id,
        client_message=message.strip(),
        checked_by=me.name,
        verdict=draft.verdict,
        reason=draft.reason,
        suggested_title=draft.suggested_title.strip() if out else "",
        suggested_scope=scope_text,
        suggested_amount_cents=amount,
        status="flagged" if out else "noted",
    )
    session.add(flag)
    session.flush()

    session.add(AgentAction(
        guild_id=job.guild_id,
        action="scope.creep_flagged",
        inputs={"job_id": str(job.id), "by": me.name, "message_len": len(message)},
        result={
            "verdict": draft.verdict,
            "reason": draft.reason,
            "suggested_title": flag.suggested_title,
            "suggested_amount_cents": flag.suggested_amount_cents,
            "estimated_hours": draft.estimated_hours if out else 0,
        },
    ))
    return flag