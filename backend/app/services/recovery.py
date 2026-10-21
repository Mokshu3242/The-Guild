"""12A Recovery loop. Rules only, no AI.

1. The pool covers an unpaid invoice -> the guild now owns that debt (pledge clause 5).
   Reminders keep going on the same PayPal invoice.
2. The client finally pays -> the pool is refilled first (money.py), the worker gets the rest.
3. A client paid the member directly (pledge clause 4) -> the member reports it, an admin
   settles it, and what the member owes the guild becomes a MemberDebt.
4. A member's open debts are taken from their next payouts first (set-off) and go to the pool.
"""
import logging
from datetime import timezone

from sqlmodel import Session, select

from app.models import (
    AgentAction, Claim, DirectPayment, Guild, Invoice, Job, Member, MemberDebt, Milestone, Payout, PoolTx,
    Reminder, utcnow,
)
from app.services import paypal_invoices, paypal_payouts
from app.services.job_status import settle_job_status
from app.services.split_engine import split_payment

logger = logging.getLogger(__name__)

PAYPAL_METHOD = {"cash": "CASH", "bank": "BANK_TRANSFER", "other": "OTHER"}


def money(c: int) -> str:
    return f"${c // 100:,}.{c % 100:02d}"


# ---------------------------------------------------------------- 1. debt moves to the guild

def log_debt_transferred(session: Session, claim: Claim, job: Job, amount: int) -> None:
    session.add(AgentAction(
        guild_id=claim.guild_id,
        action="recovery.debt_transferred",
        inputs={"claim_id": str(claim.id), "invoice_id": str(claim.invoice_id), "job_id": str(job.id)},
        result={"client": job.client_name, "covered_cents": amount},
    ))


# ---------------------------------------------------------------- 2. client pays after a claim

def note_recovery(session: Session, claim: Claim, job: Job, recovered: int, covered: int) -> None:
    """Called from money.py when part or all of a covered invoice comes back."""
    claim.recovered_cents += recovered
    claim.recovered_at = utcnow()
    session.add(claim)
    session.add(AgentAction(
        guild_id=claim.guild_id,
        action="recovery.pool_refilled",
        inputs={"claim_id": str(claim.id), "invoice_id": str(claim.invoice_id), "job_id": str(job.id)},
        result={"client": job.client_name, "recovered_cents": claim.recovered_cents, "covered_cents": covered,
                "whole": claim.recovered_cents >= covered},
    ))


# ---------------------------------------------------------------- 4. set-off

def open_debts(session: Session, member_id) -> list[MemberDebt]:
    return session.exec(
        select(MemberDebt)
        .where(MemberDebt.member_id == member_id, MemberDebt.status == "open")
        .order_by(MemberDebt.created_at)
    ).all()


def apply_set_off(session: Session, guild: Guild, member: Member, available: int, job: Job) -> int:
    """Take what the member owes from a payout they're about to get. Returns the cents taken.

    The money stays with the guild and goes into the pool. The caller has the guild row locked.
    """
    taken = 0
    for debt in open_debts(session, member.id):
        if available - taken <= 0:
            break
        due = debt.amount_cents - debt.repaid_cents
        take = min(due, available - taken)
        if take <= 0:
            continue
        debt.repaid_cents += take
        if debt.repaid_cents >= debt.amount_cents:
            debt.status, debt.closed_at = "repaid", utcnow()
        session.add(debt)
        taken += take
    if taken:
        guild.pool_balance += taken
        session.add(guild)
        session.add(PoolTx(guild_id=guild.id, amount=taken, direction="in", source="set_off"))
        session.add(AgentAction(
            guild_id=guild.id,
            action="recovery.set_off",
            inputs={"member": member.name, "job_id": str(job.id)},
            result={"taken_cents": taken, "client": job.client_name},
        ))
    return taken


# ---------------------------------------------------------------- 3. paid directly

def _invoice_job(session: Session, invoice: Invoice) -> tuple[Milestone, Job]:
    ms = session.get(Milestone, invoice.milestone_id)
    return ms, session.get(Job, ms.job_id)


def owed_breakdown(session: Session, invoice: Invoice, job: Job) -> dict:
    """What the member owes the guild if the client paid them the whole invoice directly."""
    guild = session.get(Guild, job.guild_id)
    has_referrer = bool(job.referrer_id and job.referrer_id != job.worker_id)
    split = split_payment(invoice.amount, has_referrer=has_referrer, worker_pct=guild.worker_pct,
                          referrer_pct=guild.referrer_pct, pool_pct=guild.pool_pct)
    claim = session.exec(select(Claim).where(Claim.invoice_id == invoice.id, Claim.status == "paid")).first()
    covered = 0
    if claim and claim.payout_id:
        covered = max(0, session.get(Payout, claim.payout_id).amount - claim.recovered_cents)
    return {
        "worker_cents": split.worker_cents,
        "referrer_cents": split.referrer_cents if has_referrer else 0,
        "pool_cents": split.pool_cents,
        "claim_cents": covered,          # the pool already paid the member for this invoice
        "owed_cents": (split.referrer_cents if has_referrer else 0) + split.pool_cents + covered,
        "has_referrer": has_referrer,
    }


def report_direct(session: Session, invoice: Invoice, me: Member, method: str, note: str) -> DirectPayment:
    """The client paid the whole invoice to the member, not through PayPal."""
    _, job = _invoice_job(session, invoice)
    if job.guild_id != me.guild_id:
        raise LookupError("Invoice not found")
    if job.worker_id != me.id:
        raise PermissionError("Only the worker on this job can report a direct payment")
    if invoice.status != "sent":
        raise ValueError(f"This invoice is {invoice.status}, so there's nothing to report")
    pending = session.exec(
        select(DirectPayment).where(DirectPayment.invoice_id == invoice.id, DirectPayment.status == "reported")
    ).first()
    if pending:
        raise ValueError("You already reported this one. An admin will settle it.")
    open_claim = session.exec(
        select(Claim).where(Claim.invoice_id == invoice.id, Claim.status.in_(["submitted", "ai_reviewed"]))
    ).first()
    if open_claim:
        raise ValueError("You have an open claim on this invoice. If the client paid you, ask an admin to reject it first.")
    if method not in PAYPAL_METHOD:
        raise ValueError("Pick cash, bank or other")
    amount = invoice.amount
    dp = DirectPayment(guild_id=job.guild_id, invoice_id=invoice.id, member_id=me.id, amount_cents=amount,
                       method=method, note=note.strip()[:500])
    session.add(dp)
    session.flush()
    session.add(AgentAction(
        guild_id=job.guild_id,
        action="direct_payment.reported",
        inputs={"by": me.name, "job_id": str(job.id), "invoice_id": str(invoice.id)},
        result={"client": job.client_name, "amount_cents": amount, "method": method},
    ))
    return dp


def settle_direct(session: Session, dp: DirectPayment, admin: Member) -> dict:
    """Close the invoice as paid outside PayPal. Callers commit.

    The guild never received this money, so nothing is split. Instead:
    - the referrer is paid their share now, fronted by the pool (real PayPal payout)
    - the member owes the guild: referrer share + pool slice + anything the pool already covered
    - that debt is taken from the member's next payouts first
    """
    if dp.status != "reported":
        raise ValueError(f"This report is already {dp.status}")
    if dp.member_id == admin.id:
        raise PermissionError("Another admin has to settle your own report")

    invoice = session.exec(select(Invoice).where(Invoice.id == dp.invoice_id).with_for_update()).one()
    if invoice.status != "sent":
        raise ValueError(f"The invoice is already {invoice.status}")
    milestone, job = _invoice_job(session, invoice)
    guild = session.exec(select(Guild).where(Guild.id == job.guild_id).with_for_update()).one()
    member = session.get(Member, dp.member_id)
    referrer = session.get(Member, job.referrer_id)
    b = owed_breakdown(session, invoice, job)

    # Referrer: paid now from the pool, so they don't wait on the member.
    batch_id = ""
    if b["referrer_cents"] > 0:
        if guild.pool_balance < b["referrer_cents"]:
            raise ValueError(
                f"The pool has {money(guild.pool_balance)}, not enough to pay {referrer.name}'s "
                f"{money(b['referrer_cents'])} referral fee now. Try again after the pool refills."
            )
        ref_payout = Payout(guild_id=guild.id, source_type="invoice", source_id=invoice.id, member_id=referrer.id,
                            amount=b["referrer_cents"], kind="referral",
                            status="missing_email" if not referrer.paypal_email else "pending")
        session.add(ref_payout)
        session.flush()
        if referrer.paypal_email:
            batch_id = paypal_payouts.send_batch_payout(
                [{"receiver_email": referrer.paypal_email, "amount_cents": ref_payout.amount,
                  "note": f"Referral fee for {job.client_name} (paid directly to {member.name})",
                  "item_id": str(ref_payout.id)}],
                batch_ref=f"DIRECT-{dp.id}",
            )
            ref_payout.paypal_batch_id, ref_payout.status = batch_id, "sent"
        guild.pool_balance -= b["referrer_cents"]
        session.add(PoolTx(guild_id=guild.id, amount=b["referrer_cents"], direction="out",
                           source="referral_fronted", external_ref=f"direct:{dp.id}"))

    # The member's own share: already in their hands. Recorded so the books add up.
    session.add(Payout(guild_id=guild.id, source_type="invoice", source_id=invoice.id, member_id=member.id,
                       amount=b["worker_cents"], kind="work", status="paid_direct"))

    debt = None
    if b["owed_cents"] > 0:
        debt = MemberDebt(guild_id=guild.id, member_id=member.id, kind="direct_payment", source_id=str(dp.id),
                          amount_cents=b["owed_cents"],
                          note=f"{job.client_name} paid {member.name} directly for {milestone.title}")
        session.add(debt)

    now = utcnow()
    invoice.status, invoice.paid_at = "paid", now
    milestone.status = "paid"
    dp.status, dp.owed_cents, dp.decided_by, dp.decided_at = "settled", b["owed_cents"], admin.name, now
    session.add_all([invoice, milestone, dp, guild])
    session.flush()
    settle_job_status(session, job)

    # Tell PayPal, so it stops sending reminders. Not fatal if it fails.
    try:
        paypal_invoices.record_payment(
            invoice.paypal_invoice_id, invoice.amount, PAYPAL_METHOD.get(dp.method, "OTHER"),
            f"Paid directly to {member.name}. Recorded by {admin.name}.",
            now.astimezone(timezone.utc).strftime("%Y-%m-%d"),
        )
    except Exception:
        logger.exception("Couldn't record the direct payment in PayPal for invoice %s", invoice.id)

    session.add(AgentAction(
        guild_id=guild.id,
        action="direct_payment.settled",
        inputs={"by": admin.name, "member": member.name, "job_id": str(job.id), "invoice_id": str(invoice.id)},
        result={"client": job.client_name, "owed_cents": b["owed_cents"], "referrer_cents": b["referrer_cents"],
                "pool_cents": b["pool_cents"], "claim_cents": b["claim_cents"], "batch_id": batch_id},
    ))
    return {"status": "settled", "owed_cents": b["owed_cents"], "breakdown": b}


def reject_direct(session: Session, dp: DirectPayment, admin: Member, note: str) -> None:
    if dp.status != "reported":
        raise ValueError(f"This report is already {dp.status}")
    dp.status, dp.decided_by, dp.decision_note, dp.decided_at = "rejected", admin.name, note.strip()[:500], utcnow()
    session.add(dp)
    session.add(AgentAction(
        guild_id=dp.guild_id,
        action="direct_payment.rejected",
        inputs={"by": admin.name, "invoice_id": str(dp.invoice_id)},
        result={"note": dp.decision_note},
    ))


def write_off(session: Session, debt: MemberDebt, admin: Member, note: str) -> None:
    if debt.status != "open":
        raise ValueError(f"This debt is already {debt.status}")
    debt.status, debt.closed_at = "written_off", utcnow()
    debt.note = (debt.note + f" | Written off by {admin.name}: {note.strip()}")[:500]
    session.add(debt)
    member = session.get(Member, debt.member_id)
    session.add(AgentAction(
        guild_id=debt.guild_id,
        action="recovery.written_off",
        inputs={"by": admin.name, "member": member.name if member else ""},
        result={"cents": debt.amount_cents - debt.repaid_cents, "note": note.strip()[:200]},
    ))


# ---------------------------------------------------------------- overview for the pool page

def overview(session: Session, me: Member) -> dict:
    is_admin = me.role == "admin"
    names = {m.id: m.name for m in session.exec(select(Member).where(Member.guild_id == me.guild_id)).all()}

    covered_rows = []
    claims = session.exec(
        select(Claim).where(Claim.guild_id == me.guild_id, Claim.status == "paid").order_by(Claim.created_at.desc())
    ).all()
    for c in claims:
        payout = session.get(Payout, c.payout_id) if c.payout_id else None
        invoice = session.get(Invoice, c.invoice_id)
        milestone, job = _invoice_job(session, invoice)
        covered = payout.amount if payout else 0
        reminders = session.exec(
            select(Reminder).where(Reminder.invoice_id == invoice.id, Reminder.sent_at.is_not(None))
        ).all()
        covered_rows.append({
            "claim_id": str(c.id),
            "job_id": str(job.id),
            "client": job.client_name,
            "milestone": milestone.title,
            "worker": names.get(c.member_id, ""),
            "covered_cents": covered,
            "recovered_cents": min(c.recovered_cents, covered),
            "invoice_cents": invoice.amount,
            "invoice_status": invoice.status,
            "covered_at": payout.created_at.isoformat() if payout else c.created_at.isoformat(),
            "recovered_at": c.recovered_at.isoformat() if c.recovered_at else None,
            "reminders_sent": len(reminders),
            "state": "whole" if covered and c.recovered_cents >= covered
                     else "member_owes" if invoice.status == "paid"
                     else "partial" if c.recovered_cents > 0 else "chasing",
        })

    debts = session.exec(
        select(MemberDebt).where(MemberDebt.guild_id == me.guild_id).order_by(MemberDebt.created_at.desc())
    ).all()
    if not is_admin:
        debts = [d for d in debts if d.member_id == me.id]

    reports = []
    if is_admin:
        for dp in session.exec(
            select(DirectPayment).where(DirectPayment.guild_id == me.guild_id, DirectPayment.status == "reported")
            .order_by(DirectPayment.created_at)
        ).all():
            invoice = session.get(Invoice, dp.invoice_id)
            milestone, job = _invoice_job(session, invoice)
            reports.append({
                "id": str(dp.id), "member": names.get(dp.member_id, ""), "is_me": dp.member_id == me.id,
                "client": job.client_name, "milestone": milestone.title, "job_id": str(job.id),
                "amount_cents": dp.amount_cents, "invoice_cents": invoice.amount, "method": dp.method,
                "note": dp.note, "created_at": dp.created_at.isoformat(),
                "would_owe": owed_breakdown(session, invoice, job),
            })

    total_cov = sum(r["covered_cents"] for r in covered_rows)
    total_rec = sum(r["recovered_cents"] for r in covered_rows)
    return {
        "covered_cents": total_cov,
        "recovered_cents": total_rec,
        "outstanding_cents": total_cov - total_rec,
        "covered": covered_rows,
        "debts": [
            {"id": str(d.id), "member": names.get(d.member_id, ""), "kind": d.kind, "amount_cents": d.amount_cents,
             "repaid_cents": d.repaid_cents, "status": d.status, "note": d.note, "created_at": d.created_at.isoformat()}
            for d in debts
        ],
        "reports": reports,
    }
