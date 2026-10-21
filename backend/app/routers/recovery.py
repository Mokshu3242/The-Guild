from typing import Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.db import get_session
from app.deps import get_current_member, require_admin
from app.models import DirectPayment, Invoice, Member, MemberDebt
from app.services import paypal_invoices, recovery

router = APIRouter(prefix="/recovery", tags=["recovery"])


class DirectIn(BaseModel):
    method: Literal["cash", "bank", "other"] = "bank"
    note: str = Field(default="", max_length=500)


class NoteIn(BaseModel):
    note: str = Field(default="", max_length=500)


def _fail(e: Exception):
    if isinstance(e, LookupError):
        raise HTTPException(404, str(e))
    if isinstance(e, PermissionError):
        raise HTTPException(403, str(e))
    raise HTTPException(400, str(e))


@router.get("")
def get_recovery(me: Member = Depends(get_current_member), session: Session = Depends(get_session)):
    return recovery.overview(session, me)


@router.post("/invoices/{invoice_id}/direct")
def report_direct(
    invoice_id: UUID,
    body: DirectIn,
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    invoice = session.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(404, "Invoice not found")
    try:
        dp = recovery.report_direct(session, invoice, me, body.method, body.note)
    except (LookupError, PermissionError, ValueError) as e:
        session.rollback()
        _fail(e)
    session.commit()
    return {"status": "reported", "id": str(dp.id), "amount_cents": dp.amount_cents}


def _report(session: Session, dp_id: UUID, admin: Member) -> DirectPayment:
    dp = session.get(DirectPayment, dp_id)
    if not dp or dp.guild_id != admin.guild_id:
        raise HTTPException(404, "Report not found")
    return dp


@router.post("/direct/{dp_id}/settle")
def settle(dp_id: UUID, admin: Member = Depends(require_admin), session: Session = Depends(get_session)):
    dp = _report(session, dp_id, admin)
    invoice = session.get(Invoice, dp.invoice_id)
    # If PayPal says the client paid there, it isn't a direct payment. The webhook will handle it.
    try:
        if paypal_invoices.get_invoice(invoice.paypal_invoice_id).get("status") == "PAID":
            raise HTTPException(400, "PayPal shows this invoice as paid through PayPal. Reject this report.")
    except httpx.HTTPError:
        pass
    try:
        result = recovery.settle_direct(session, dp, admin)
    except (LookupError, PermissionError, ValueError) as e:
        session.rollback()
        _fail(e)
    except httpx.HTTPStatusError as e:
        session.rollback()
        raise HTTPException(502, f"PayPal payout to the referrer failed: {e.response.text[:300]}")
    session.commit()
    return result


@router.post("/direct/{dp_id}/reject")
def reject(dp_id: UUID, body: NoteIn, admin: Member = Depends(require_admin), session: Session = Depends(get_session)):
    dp = _report(session, dp_id, admin)
    try:
        recovery.reject_direct(session, dp, admin, body.note)
    except ValueError as e:
        _fail(e)
    session.commit()
    return {"status": "rejected"}


@router.post("/debts/{debt_id}/write-off")
def write_off(debt_id: UUID, body: NoteIn, admin: Member = Depends(require_admin), session: Session = Depends(get_session)):
    debt = session.get(MemberDebt, debt_id)
    if not debt or debt.guild_id != admin.guild_id:
        raise HTTPException(404, "Debt not found")
    if debt.member_id == admin.id:
        raise HTTPException(403, "Another admin has to write off your own debt")
    if len(body.note.strip()) < 5:
        raise HTTPException(400, "Say why in a few words")
    try:
        recovery.write_off(session, debt, admin, body.note)
    except ValueError as e:
        _fail(e)
    session.commit()
    return {"status": "written_off"}
