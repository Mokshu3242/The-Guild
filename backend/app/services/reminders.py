import logging

import httpx
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.models import AgentAction, Invoice, Job, Milestone, Reminder, utcnow
from app.services import paypal_invoices
from app.services.money import process_paid_invoice
from app.services.reminder_writer import write_reminder

logger = logging.getLogger(__name__)

TIER_DAYS = {1: 3, 2: 8, 3: 14}


def next_tier(session: Session, invoice: Invoice, days: int) -> int | None:
    """The next tier in order, if it's due. Never skips a tier."""
    sent = session.exec(select(Reminder.tier).where(Reminder.invoice_id == invoice.id)).all()
    nxt = (max(sent) + 1) if sent else 1
    if nxt > 3 or days < TIER_DAYS[nxt]:
        return None
    # turn on after video
    # if sent:
    #     last = session.exec(
    #         select(Reminder.sent_at).where(Reminder.invoice_id == invoice.id)
    #         .order_by(Reminder.tier.desc())
    #     ).first()
    #     if last and (utcnow() - last).days < 2:
    #         return None
    return nxt


def remind_one(session: Session, invoice: Invoice, guild_id) -> dict:
    """Send the next due reminder for one invoice. Commits on its own."""
    if invoice.status != "sent" or not invoice.sent_at:
        return {"status": "skipped", "reason": f"invoice is {invoice.status}"}

    # Did they actually pay? Don't nag a paying client.
    if paypal_invoices.get_invoice(invoice.paypal_invoice_id).get("status") == "PAID":
        result = process_paid_invoice(session, invoice.id, source="reminder_check")
        session.commit()
        return {"status": "already_paid", "detail": result["status"]}

    days = (utcnow() - invoice.sent_at).days
    tier = next_tier(session, invoice, days)
    if tier is None:
        return {"status": "not_due", "days_overdue": days}

    draft, written_by = write_reminder(session, invoice, tier, days)

    # Reserve the tier first. The unique rule stops two runs sending the same tier.
    reminder = Reminder(guild_id=guild_id, invoice_id=invoice.id, tier=tier,
                        subject=draft.subject, body=draft.body, days_overdue=days, written_by=written_by)
    session.add(reminder)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        return {"status": "already_sent", "tier": tier}

    try:
        paypal_invoices.remind_invoice(invoice.paypal_invoice_id, tier, draft.subject, draft.body)
    except httpx.HTTPError:
        session.rollback()
        logger.exception("PayPal reminder failed for invoice %s", invoice.id)
        return {"status": "paypal_failed", "tier": tier}

    reminder.sent_at = utcnow()
    session.add(AgentAction(
        guild_id=guild_id, action="reminder.sent",
        inputs={"invoice_id": str(invoice.id), "tier": tier, "days_overdue": days},
        result={"subject": draft.subject, "written_by": written_by},
    ))
    session.commit()
    return {"status": "sent", "tier": tier, "days_overdue": days, "subject": draft.subject}


def run_all(session: Session) -> list[dict]:
    """Cron entry. One reminder at most per invoice per run."""
    rows = session.exec(
        select(Invoice, Job.guild_id)
        .join(Milestone, Invoice.milestone_id == Milestone.id)
        .join(Job, Milestone.job_id == Job.id)
        .where(Invoice.status == "sent")
    ).all()
    results = []
    for invoice, guild_id in rows:
        try:
            r = remind_one(session, invoice, guild_id)
        except Exception:
            session.rollback()
            logger.exception("Reminder run failed for invoice %s", invoice.id)
            r = {"status": "error"}
        results.append({"invoice_id": str(invoice.id), **r})
    return results