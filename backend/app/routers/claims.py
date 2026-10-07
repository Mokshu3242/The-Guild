from typing import Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.db import get_session
from app.deps import get_current_member, require_admin
from app.models import AgentAction, Claim, Guild, Invoice, Job, Member, Milestone, utcnow
from app.services import paypal_invoices
from app.services.ai import AIError
from app.services.claim_reviewer import review_claim
from app.services.claims import pay_claim
from app.services.money import process_paid_invoice

router = APIRouter(prefix="/claims", tags=["claims"])


class CreateClaimIn(BaseModel):
    invoice_id: UUID
    statement: str = Field(min_length=20, max_length=3000)
    evidence_urls: list[str] = Field(default_factory=list, max_length=10)

class DecisionIn(BaseModel):
    decision: Literal["approve", "reject"]
    note: str = Field(default="", max_length=1000)


def _claim_in_my_guild(session: Session, claim_id: UUID, me: Member) -> Claim:
    claim = session.get(Claim, claim_id)
    if not claim or claim.guild_id != me.guild_id:
        raise HTTPException(404, "Claim not found")
    return claim


@router.post("")
def create_claim(
    body: CreateClaimIn,
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    invoice = session.get(Invoice, body.invoice_id)
    if not invoice:
        raise HTTPException(404, "Invoice not found")
    job = session.get(Job, session.get(Milestone, invoice.milestone_id).job_id)
    if job.guild_id != me.guild_id:
        raise HTTPException(404, "Invoice not found")

    # --- Pool rules ---
    if job.worker_id != me.id:
        raise HTTPException(403, "Only the worker on this job can file a claim")
    if invoice.status != "sent":
        raise HTTPException(400, f"Only unpaid sent invoices can be claimed (this one is {invoice.status})")
    open_claim = session.exec(
        select(Claim).where(Claim.invoice_id == invoice.id).where(Claim.status != "rejected")
    ).first()
    if open_claim:
        raise HTTPException(400, "This invoice already has a claim")

    guild = session.get(Guild, job.guild_id)
    now = utcnow()
    if (now - me.joined_at).days < guild.claim_wait_days:
        raise HTTPException(400, f"Members must be in the guild {guild.claim_wait_days} days before claiming")
    if (now - invoice.sent_at).days < guild.claim_overdue_days:
        raise HTTPException(400, f"Invoices must be {guild.claim_overdue_days} days overdue before claiming")

    # --- Did the client actually pay? Check PayPal first ---
    try:
        paypal_status = paypal_invoices.get_invoice(invoice.paypal_invoice_id).get("status")
    except httpx.HTTPStatusError:
        raise HTTPException(502, "Couldn't check the invoice with PayPal, try again")
    if paypal_status == "PAID":
        result = process_paid_invoice(session, invoice.id, source="claim_check")
        session.commit()
        raise HTTPException(409, f"Good news: the client paid. Your payout was sent instead ({result['status']}).")

    # --- File it ---
    claim = Claim(
        guild_id=guild.id,
        member_id=me.id,
        invoice_id=invoice.id,
        statement=body.statement,
        evidence_urls=body.evidence_urls,
    )
    job.status = "disputed"
    session.add_all([claim, job])
    session.commit()
    session.refresh(claim)

    # --- AI review right away ---
    try:
        review_claim(session, claim)
        session.commit()
        session.refresh(claim)
        return {"claim": claim, "ai_review": "done"}
    except AIError:
        session.rollback()
        session.refresh(claim)
        return {"claim": claim, "ai_review": "failed, an admin can retry it"}


@router.post("/{claim_id}/review")
def rerun_review(
    claim_id: UUID,
    admin: Member = Depends(require_admin),
    session: Session = Depends(get_session),
):
    claim = _claim_in_my_guild(session, claim_id, admin)
    if claim.status not in ("submitted", "ai_reviewed"):
        raise HTTPException(400, f"Can't review a claim that is {claim.status}")
    try:
        verdict = review_claim(session, claim)
    except AIError as e:
        session.rollback()
        raise HTTPException(502, f"AI review failed: {e}")
    session.commit()
    return verdict


def _is_override(ai_verdict: str, decision: str) -> bool:
    """True when the admin goes against the AI's recommendation."""
    if decision == "approve":
        return ai_verdict != "approve"
    return ai_verdict == "approve"


@router.post("/{claim_id}/decide")
def decide(
    claim_id: UUID,
    body: DecisionIn,
    admin: Member = Depends(require_admin),
    session: Session = Depends(get_session),
):
    claim = _claim_in_my_guild(session, claim_id, admin)
    if claim.member_id == admin.id:
        raise HTTPException(403, "You can't decide on your own claim")
    if claim.status == "paid":
        return {"status": "already_paid", "claim_id": str(claim.id)}

    note = body.note.strip()
    override = _is_override(claim.ai_verdict, body.decision)
    if override and len(note) < 10:
        raise HTTPException(
            400,
            f"The AI recommended '{claim.ai_verdict}'. To {body.decision} anyway, "
            "add a note of at least 10 characters explaining why.",
        )

    if body.decision == "reject":
        claim.status = "rejected"
        claim.admin_decision = "rejected"
        claim.admin_note = note
        invoice = session.get(Invoice, claim.invoice_id)
        job = session.get(Job, session.get(Milestone, invoice.milestone_id).job_id)
        job.status = "in_progress"
        session.add_all([claim, job])
        session.add(AgentAction(
            guild_id=claim.guild_id,
            action="claim.rejected",
            inputs={
                "claim_id": str(claim.id),
                "rejected_by": admin.name,
                "ai_verdict": claim.ai_verdict,
                "override": override,
                "admin_note": note,
            },
            result={"pool_unchanged": True},
        ))
        session.commit()
        return {"status": "rejected", "claim_id": str(claim.id), "override": override}

    try:
        result = pay_claim(session, claim.id, admin, note=note, override=override)
        session.commit()
        return {**result, "override": override}
    except ValueError as e:
        session.rollback()
        raise HTTPException(400, str(e))
    except httpx.HTTPStatusError as e:
        session.rollback()
        raise HTTPException(502, f"PayPal payout failed: {e.response.text[:300]}")


@router.get("/mine")
def my_claims(
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    return session.exec(
        select(Claim).where(Claim.member_id == me.id).order_by(Claim.created_at.desc())
    ).all()


@router.get("")
def guild_claims(
    admin: Member = Depends(require_admin),
    session: Session = Depends(get_session),
):
    return session.exec(
        select(Claim).where(Claim.guild_id == admin.guild_id).order_by(Claim.created_at.desc())
    ).all()