import logging
from uuid import UUID

from sqlmodel import Session, select

from app.models import (
    AgentAction, Guild, Invoice, Job, Member, Milestone, Payout, PoolTx, utcnow,
)
from app.services import paypal_payouts
from app.services.split_engine import split_payment

logger = logging.getLogger(__name__)


def process_paid_invoice(session: Session, invoice_id: UUID, source: str) -> dict:
    """Run the money flow for a paid invoice. Safe to call twice.

    Locks the invoice row so a webhook and a sync can't both pay out.
    The caller commits.
    """
    invoice = session.exec(
        select(Invoice).where(Invoice.id == invoice_id).with_for_update()
    ).one()

    if invoice.status == "paid":
        return {"status": "already_paid", "invoice_id": str(invoice.id)}

    milestone = session.get(Milestone, invoice.milestone_id)
    job = session.get(Job, milestone.job_id)
    guild = session.get(Guild, job.guild_id)

    if not job.worker_id:
        raise ValueError(f"Job {job.id} has no worker")
    worker = session.get(Member, job.worker_id)
    referrer = session.get(Member, job.referrer_id)
    has_referrer = referrer is not None and referrer.id != worker.id

    split = split_payment(
        amount_cents=invoice.amount,
        has_referrer=has_referrer,
        worker_pct=guild.worker_pct,
        referrer_pct=guild.referrer_pct,
        pool_pct=guild.pool_pct,
    )

    # 1. Pool slice stays in the Guild account
    if split.pool_cents > 0:
        guild.pool_balance += split.pool_cents
        session.add(guild)
        session.add(PoolTx(
            guild_id=guild.id,
            amount=split.pool_cents,
            direction="in",
            source="referral_slice",
        ))

    # 2. Ledger rows
    shares = [(worker, split.worker_cents, "work")]
    if has_referrer:
        shares.append((referrer, split.referrer_cents, "referral"))

    rows: list[tuple[Payout, Member]] = []
    for member, cents, kind in shares:
        if cents <= 0:
            continue
        rows.append((Payout(
            guild_id=guild.id,
            source_type="invoice",
            source_id=invoice.id,
            member_id=member.id,
            amount=cents,
            kind=kind,
            status="missing_email" if not member.paypal_email else "pending",
        ), member))

    # 3. One Payouts batch for everyone with a PayPal email
    items = [
        {
            "receiver_email": m.paypal_email,
            "amount_cents": p.amount,
            "note": f"{p.kind.title()} payout for {job.client_name}",
            "item_id": str(p.id),
        }
        for p, m in rows if m.paypal_email
    ]
    batch_id = ""
    if items:
        try:
            batch_id = paypal_payouts.send_batch_payout(items, batch_ref=str(invoice.id))
        except Exception:
            logger.exception("Payout batch failed for invoice %s", invoice.id)

    for p, m in rows:
        if m.paypal_email:
            p.paypal_batch_id = batch_id
            p.status = "sent" if batch_id else "failed"
        session.add(p)

    # 4. Statuses
    invoice.status = "paid"
    invoice.paid_at = utcnow()
    milestone.status = "paid"
    job.status = "paid"
    session.add_all([invoice, milestone, job])

    # 5. Log for the dashboard
    result = {
        "worker_cents": split.worker_cents,
        "referrer_cents": split.referrer_cents,
        "pool_cents": split.pool_cents,
        "payout_batch_id": batch_id,
    }
    session.add(AgentAction(
        guild_id=guild.id,
        action="invoice.paid.split",
        inputs={"invoice_id": str(invoice.id), "source": source, "amount": invoice.amount},
        result=result,
    ))

    return {"status": "processed", "invoice_id": str(invoice.id), **result}