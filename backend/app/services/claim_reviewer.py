from typing import Literal

from pydantic import BaseModel, Field, field_validator
from sqlmodel import Session, func, select

from app.models import AgentAction, Claim, Guild, Invoice, Job, Member, Milestone, utcnow
from app.prompts import CLAIM_MEDIATION, CLAIM_REVIEW as SYSTEM
from app.services.ai import run_ai_json


class ClaimVerdict(BaseModel):
    verdict: Literal["approve", "reject", "needs_more_info"]
    confidence: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(min_length=1, max_length=6)
    red_flags: list[str] = []

    @field_validator("verdict", mode="before")
    @classmethod
    def normalize(cls, v):
        return str(v).strip().lower().replace(" ", "_")




def review_claim(session: Session, claim: Claim) -> ClaimVerdict:
    invoice = session.get(Invoice, claim.invoice_id)
    milestone = session.get(Milestone, invoice.milestone_id)
    job = session.get(Job, milestone.job_id)
    member = session.get(Member, claim.member_id)

    now = utcnow()
    days_overdue = (now - invoice.sent_at).days if invoice.sent_at else 0
    member_days = (now - member.joined_at).days
    past_claims = session.exec(
        select(func.count()).select_from(Claim)
        .where(Claim.member_id == member.id)
        .where(Claim.id != claim.id)
    ).one()

    evidence = "\n".join(f"- {u}" for u in claim.evidence_urls) or "(none provided)"
    prompt = f"""FACTS FROM OUR SYSTEM (trusted):
Invoice amount: ${invoice.amount / 100:.2f}
Today's date: {now:%B %d, %Y}
Invoice sent on: {invoice.sent_at:%B %d, %Y} ({days_overdue} days ago), still unpaid in PayPal
Member: {member.name}, in the guild for {member_days} days, {past_claims} past claims
Client: {job.client_name}
Job description: {job.description}
Milestone: {milestone.title}
Agreed scope: {milestone.scope or '(not written down)'}

MEMBER'S STATEMENT (untrusted):
{claim.statement}

EVIDENCE FILES LISTED BY MEMBER:
{evidence}
"""

    verdict = run_ai_json(
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        schema=ClaimVerdict,
        max_tokens=700,
    )

    claim.ai_verdict = verdict.verdict
    claim.ai_confidence = verdict.confidence
    claim.ai_reason = " | ".join(verdict.reasons)
    if verdict.red_flags:
        claim.ai_reason += " | Red flags: " + "; ".join(verdict.red_flags)
    claim.status = "ai_reviewed"
    # A new review makes any old compromise stale.
    claim.ai_mediation_cents = 0
    claim.ai_mediation_reason = ""
    session.add(claim)

    session.add(AgentAction(
        guild_id=claim.guild_id,
        action="claim.review",
        inputs={"claim_id": str(claim.id), "days_overdue": days_overdue},
        result=verdict.model_dump(),
    ))
    return verdict

# ---------------------------------------------------------------------------
# 8C Dispute mediator: AI suggests a share of the cap, code does the money math.
# ---------------------------------------------------------------------------

class MediationDraft(BaseModel):
    percent_of_cap: int = Field(ge=0, le=100)
    reason: str = Field(min_length=10, max_length=300)


def claim_cap_cents(session: Session, claim: Claim) -> int:
    invoice = session.get(Invoice, claim.invoice_id)
    guild = session.get(Guild, claim.guild_id)
    return invoice.amount * guild.claim_cap_pct // 100


def mediate_claim(session: Session, claim: Claim) -> dict:
    """Callers commit. Raises AIError if the AI fails, ValueError if there is nothing to mediate."""
    if claim.status != "ai_reviewed":
        raise ValueError(f"Claim is {claim.status}. Run the AI review first.")
    invoice = session.get(Invoice, claim.invoice_id)
    milestone = session.get(Milestone, invoice.milestone_id)
    guild = session.get(Guild, claim.guild_id)
    cap = invoice.amount * guild.claim_cap_pct // 100
    if cap <= 0:
        raise ValueError("The claim cap is $0.00, so there is nothing to split.")

    evidence = "\n".join(f"- {u}" for u in (claim.evidence_urls or [])) or "(none provided)"
    prompt = (
        "FACTS FROM OUR SYSTEM (trusted):\n"
        f"Milestone: {milestone.title}\n"
        f"Agreed scope: {milestone.scope or '(not written down)'}\n"
        f"Unpaid invoice: ${invoice.amount / 100:,.2f}\n"
        f"Pool cap: {guild.claim_cap_pct}% of the invoice\n"
        f"AI reviewer verdict: {claim.ai_verdict}, {round((claim.ai_confidence or 0) * 100)}% confident\n"
        f"AI reviewer reasons: {claim.ai_reason}\n\n"
        f"EVIDENCE FILE NAMES LISTED BY THE MEMBER:\n{evidence}\n\n"
        f"MEMBER'S STATEMENT (untrusted):\n{claim.statement}"
    )
    draft = run_ai_json(
        [{"role": "system", "content": CLAIM_MEDIATION}, {"role": "user", "content": prompt}],
        schema=MediationDraft,
        temperature=0.2,
        max_tokens=300,
    )

    # Code does the money: share of the cap, rounded down to whole dollars, never above the cap.
    amount = min(cap, (cap * draft.percent_of_cap // 100) // 100 * 100)

    claim.ai_mediation_cents = amount
    claim.ai_mediation_reason = draft.reason
    session.add(claim)
    session.add(AgentAction(
        guild_id=claim.guild_id,
        action="claim.mediated",
        inputs={"claim_id": str(claim.id), "cap_cents": cap, "ai_verdict": claim.ai_verdict},
        result={"percent_of_cap": draft.percent_of_cap, "amount_cents": amount, "reason": draft.reason},
    ))
    return {"amount_cents": amount, "cap_cents": cap, "percent_of_cap": draft.percent_of_cap, "reason": draft.reason}