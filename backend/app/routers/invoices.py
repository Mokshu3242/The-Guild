import logging
import uuid
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.db import get_session
from app.deps import get_current_member
from app.services import paypal_invoices
from app.services.money import process_paid_invoice
from app.deps import get_current_member, require_admin
from app.models import Invoice, Job, Member, Milestone, Reminder, utcnow
from app.services.reminders import remind_one

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/invoices", tags=["invoices"])


def _paypal_error(e: httpx.HTTPStatusError) -> HTTPException:
    logger.error("PayPal error %s: %s", e.response.status_code, e.response.text)
    return HTTPException(502, f"PayPal error: {e.response.text[:300]}")


def _invoice_in_my_guild(session: Session, invoice_id: UUID, me: Member):
    invoice = session.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(404, "Invoice not found")
    milestone = session.get(Milestone, invoice.milestone_id)
    job = session.get(Job, milestone.job_id)
    if job.guild_id != me.guild_id:
        raise HTTPException(404, "Invoice not found")
    return invoice, milestone, job


@router.post("/milestones/{milestone_id}/send")
def send_milestone_invoice(
    milestone_id: UUID,
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    milestone = session.get(Milestone, milestone_id)
    if not milestone:
        raise HTTPException(404, "Milestone not found")
    job = session.get(Job, milestone.job_id)
    if job.guild_id != me.guild_id:
        raise HTTPException(404, "Milestone not found")
    if me.id not in (job.referrer_id, job.worker_id) and me.role != "admin":
        raise HTTPException(403, "Only the poster, the worker, or an admin can invoice")
    if not job.worker_id:
        raise HTTPException(400, "Assign a worker before sending an invoice")

    invoice = session.exec(
        select(Invoice).where(Invoice.milestone_id == milestone.id)
    ).first()
    if invoice and invoice.status in ("sent", "paid"):
        raise HTTPException(400, f"Invoice already {invoice.status}")

    try:
        # Step 1: create a draft and save it right away
        if invoice is None:
            paypal_id = paypal_invoices.create_invoice(
                invoice_number=f"GUILD-{uuid.uuid4().hex[:12]}",
                client_email=job.client_email,
                amount_cents=milestone.amount,
                item_name=milestone.title,
                note=f"Milestone for {job.client_name}",
            )
            invoice = Invoice(
                milestone_id=milestone.id,
                paypal_invoice_id=paypal_id,
                amount=milestone.amount,
                status="draft",
            )
            session.add(invoice)
            session.commit()
            session.refresh(invoice)

        # Step 2: send it and grab the pay link
        paypal_invoices.send_invoice(invoice.paypal_invoice_id)
        details = paypal_invoices.get_invoice(invoice.paypal_invoice_id)
    except httpx.HTTPStatusError as e:
        raise _paypal_error(e)

    invoice.pay_url = paypal_invoices.payer_url(details)
    invoice.status = "sent"
    invoice.sent_at = utcnow()
    milestone.status = "invoiced"
    job.status = "in_progress"
    session.add_all([invoice, milestone, job])
    session.commit()
    session.refresh(invoice)
    return invoice


@router.get("")
def list_invoices(
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    return session.exec(
        select(Invoice)
        .join(Milestone, Invoice.milestone_id == Milestone.id)
        .join(Job, Milestone.job_id == Job.id)
        .where(Job.guild_id == me.guild_id)
        .order_by(Invoice.sent_at.desc())
    ).all()


@router.get("/{invoice_id}")
def get_invoice(
    invoice_id: UUID,
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    invoice, _, _ = _invoice_in_my_guild(session, invoice_id, me)
    return invoice


@router.post("/{invoice_id}/sync")
def sync_invoice(
    invoice_id: UUID,
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Ask PayPal for the real status. Runs the money flow only if truly paid.

    Backup for when Render is asleep and misses the webhook.
    """
    invoice, _, _ = _invoice_in_my_guild(session, invoice_id, me)
    if invoice.status == "paid":
        return {"status": "already_paid", "invoice_id": str(invoice.id)}

    try:
        details = paypal_invoices.get_invoice(invoice.paypal_invoice_id)
    except httpx.HTTPStatusError as e:
        raise _paypal_error(e)

    paypal_status = details.get("status", "UNKNOWN")
    if paypal_status != "PAID":
        return {"status": "not_paid_yet", "paypal_status": paypal_status}

    result = process_paid_invoice(session, invoice.id, source="sync")
    session.commit()
    return result

@router.post("/{invoice_id}/remind")
def remind_now(
    invoice_id: UUID,
    admin: Member = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """Send the next due reminder for THIS invoice only."""
    invoice, _, job = _invoice_in_my_guild(session, invoice_id, admin)
    try:
        return remind_one(session, invoice, job.guild_id)
    except httpx.HTTPStatusError as e:
        session.rollback()
        raise _paypal_error(e)


@router.get("/{invoice_id}/reminders")
def invoice_reminders(
    invoice_id: UUID,
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    _invoice_in_my_guild(session, invoice_id, me)
    return session.exec(
        select(Reminder).where(Reminder.invoice_id == invoice_id).order_by(Reminder.tier)
    ).all()