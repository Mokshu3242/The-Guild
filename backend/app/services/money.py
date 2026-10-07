import logging
from uuid import UUID

from sqlmodel import Session, select

from app.models import (
    AgentAction, Claim, Guild, Invoice, Job, Member, Milestone, Payout, PoolTx, utcnow,
)
from app.services import paypal_payouts
from app.services.split_engine import split_payment

logger = logging.getLogger(__name__)


def process_paid_invoice(session: Session, invoice_id: UUID, source: str) -> dict:
    """Run the money flow for a paid invoice. Safe to call twice.

    If the pool already covered this invoice through a claim, that amount
    is taken from the worker's share and returned to the pool.
    The caller commits.
    """
    invoice = session.exec(
        select(Invoice).where(Invoice.id == invoice_id).with_for_update()
    ).one()
    if invoice.status == "paid":
        return {"status": "already_paid", "invoice_id": str(invoice.id)}

    milestone = session.get(Milestone, invoice.milestone_id)
    job = session.get(Job, milestone.job_id)
    guild = session.exec(select(Guild).where(Guild.id == job.guild_id).with_for_update()).one()

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

    # Recovery: did the pool already cover this invoice?
    worker_cents = split.worker_cents
    recovered = 0
    paid_claim = session.exec(
        select(Claim).where(Claim.invoice_id == invoice.id).where(Claim.status == "paid")
    ).first()
    if paid_claim and paid_claim.payout_id:
        claim_payout = session.get(Payout, paid_claim.payout_id)
        recovered = min(claim_payout.amount, worker_cents)
        worker_cents -= recovered

    # 1. Pool: the usual slice, plus any recovery
    for amount, src in ((split.pool_cents, "referral_slice"), (recovered, "recovery")):
        if amount > 0:
            guild.pool_balance += amount
            session.add(PoolTx(guild_id=guild.id, amount=amount, direction="in", source=src))
    session.add(guild)

    # 2. Ledger rows
    shares = [(worker, worker_cents, "work")]
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

    # 3. One Payouts batch
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

    # 5. Log
    result = {
        "worker_cents": worker_cents,
        "referrer_cents": split.referrer_cents if has_referrer else 0,
        "pool_cents": split.pool_cents,
        "recovered_cents": recovered,
        "payout_batch_id": batch_id,
    }
    session.add(AgentAction(
        guild_id=guild.id,
        action="invoice.paid.split",
        inputs={"invoice_id": str(invoice.id), "source": source, "amount": invoice.amount},
        result=result,
    ))
    return {"status": "processed", "invoice_id": str(invoice.id), **result}