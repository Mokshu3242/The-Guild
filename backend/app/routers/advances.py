from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.db import get_session
from app.deps import get_current_member, require_admin
from app.models import Advance, Invoice, Job, Member, Milestone
from app.services import advances as svc

router = APIRouter(prefix="/advances", tags=["advances"])


class NoteIn(BaseModel):
    note: str = Field(default="", max_length=500)


def _invoice(session: Session, invoice_id: UUID, me: Member) -> Invoice:
    invoice = session.get(Invoice, invoice_id)
    if invoice:
        job = session.get(Job, session.get(Milestone, invoice.milestone_id).job_id)
        if job.guild_id == me.guild_id:
            return invoice
    raise HTTPException(404, "Invoice not found")


def _advance(session: Session, advance_id: UUID, me: Member) -> Advance:
    adv = session.get(Advance, advance_id)
    if not adv or adv.guild_id != me.guild_id:
        raise HTTPException(404, "Advance not found")
    return adv


@router.get("")
def list_advances(me: Member = Depends(get_current_member), session: Session = Depends(get_session)):
    """Admins see the whole guild. Members see their own."""
    return svc.overview(session, me)


@router.get("/invoices/{invoice_id}/quote")
def quote(invoice_id: UUID, me: Member = Depends(get_current_member), session: Session = Depends(get_session)):
    """Rules only, no AI. What the worker would get now, and why not if they can't."""
    invoice = _invoice(session, invoice_id, me)
    c = svc.check(session, invoice, me)
    current = session.exec(
        select(Advance).where(Advance.invoice_id == invoice.id).order_by(Advance.created_at.desc())
    ).first()
    c.pop("client_facts", None)
    c["current"] = {"id": str(current.id), "status": current.status, "advance_cents": current.advance_cents,
                    "fee_cents": current.fee_cents, "decision_note": current.decision_note} if current else None
    return c


@router.post("/invoices/{invoice_id}/request")
def request_advance(invoice_id: UUID, me: Member = Depends(get_current_member), session: Session = Depends(get_session)):
    invoice = _invoice(session, invoice_id, me)
    try:
        adv = svc.request(session, invoice, me)
    except ValueError as e:
        session.rollback()
        raise HTTPException(400, str(e))
    session.commit()
    return {"id": str(adv.id), "status": adv.status, "advance_cents": adv.advance_cents,
            "fee_cents": adv.fee_cents, "explanation": adv.explanation}


@router.post("/{advance_id}/approve")
def approve(advance_id: UUID, admin: Member = Depends(require_admin), session: Session = Depends(get_session)):
    adv = _advance(session, advance_id, admin)
    try:
        result = svc.approve(session, adv, admin)
    except PermissionError as e:
        session.rollback()
        raise HTTPException(403, str(e))
    except ValueError as e:
        session.rollback()
        raise HTTPException(400, str(e))
    except httpx.HTTPStatusError as e:
        session.rollback()
        raise HTTPException(502, f"PayPal payout failed: {e.response.text[:300]}")
    session.commit()
    return result


@router.post("/{advance_id}/decline")
def decline(advance_id: UUID, body: NoteIn, admin: Member = Depends(require_admin),
            session: Session = Depends(get_session)):
    adv = _advance(session, advance_id, admin)
    try:
        svc.decline(session, adv, admin, body.note)
    except ValueError as e:
        raise HTTPException(400, str(e))
    session.commit()
    return {"status": "declined"}
