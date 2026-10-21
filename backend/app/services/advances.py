"""12B Paid on day one.

Rules decide. The AI writes one note for the admin. An admin approves.

An advance is the pool paying part of the worker's own share early:
- amount: 70% of the invoice, capped at $1,000, and never more than the worker's share can repay
- fee: 2% of the advance, kept by the pool
- the client pays -> advance + fee come off the worker's share first (money.py), the rest is paid as usual
- the client hasn't paid 45 days after the advance -> it becomes a MemberDebt, and 12A's set-off collects it
- an advance means the member carries the client risk, so no claim on that invoice
"""
import logging
import re
from datetime import timedelta

from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.models import (
    Advance, AgentAction, Claim, Guild, Invoice, Job, Member, MemberDebt, Milestone, Payout, PoolTx, utcnow,
)
from app.prompts import ADVANCE_NOTE
from app.services import paypal_payouts
from app.services.agreements import agreement_for_milestone, pledge_signed
from app.services.ai import AIError, run_ai_json
from app.services.client_risk import client_history, risk_level
from app.services.split_engine import split_payment

logger = logging.getLogger(__name__)

ADVANCE_PCT = 70
FEE_PCT = 2
MAX_ADVANCE_CENTS = 100_000      # $1,000
REPAY_DAYS = 45
POOL_SHARE_LIMIT = 50            # one advance can use at most half the pool

ACTIVE = ("pending", "paid")
BLOCKS_CLAIM = ("pending", "paid", "defaulted")


def money(c: int) -> str:
    return f"${c // 100:,}.{c % 100:02d}"


class Note(BaseModel):
    note: str = Field(min_length=10, max_length=400)


# ---------------------------------------------------------------- the math

def worker_share(guild: Guild, job: Job, amount: int) -> int:
    has_referrer = bool(job.referrer_id and job.referrer_id != job.worker_id)
    return split_payment(amount, has_referrer=has_referrer, worker_pct=guild.worker_pct,
                         referrer_pct=guild.referrer_pct, pool_pct=guild.pool_pct).worker_cents


def amounts(guild: Guild, job: Job, invoice_cents: int) -> dict:
    share = worker_share(guild, job, invoice_cents)
    # advance + fee must fit inside the worker's share, so the pool is always paid back in full
    advance = min(invoice_cents * ADVANCE_PCT // 100, MAX_ADVANCE_CENTS, share * 100 // (100 + FEE_PCT))
    fee = advance * FEE_PCT // 100
    return {
        "invoice_cents": invoice_cents,
        "worker_share_cents": share,
        "advance_cents": advance,
        "fee_cents": fee,
        "repay_cents": advance + fee,
        "later_cents": share - advance - fee,   # what the worker still gets when the client pays
    }


# ---------------------------------------------------------------- the rules

def _context(session: Session, invoice: Invoice) -> tuple[Milestone, Job, Guild]:
    ms = session.get(Milestone, invoice.milestone_id)
    job = session.get(Job, ms.job_id)
    return ms, job, session.get(Guild, job.guild_id)


def check(session: Session, invoice: Invoice, member: Member, ignore: Advance | None = None) -> dict:
    """Every rule, in plain words. Same facts always give the same answer.

    ignore: the advance being approved, so it doesn't block itself.
    """
    ms, job, guild = _context(session, invoice)
    a = amounts(guild, job, invoice.amount)
    blocks: list[str] = []

    def active(q):
        return [x for x in session.exec(q).all() if not ignore or x.id != ignore.id]

    # The job
    if job.worker_id != member.id:
        blocks.append("Only the worker on this job can be paid early.")
    if invoice.status != "sent":
        blocks.append(f"The invoice is {invoice.status}. Only a sent, unpaid invoice can be paid early.")
    if not agreement_for_milestone(session, job, ms):
        blocks.append("The client hasn't accepted an agreement that covers this milestone.")
    if not ms.client_approved_at:
        blocks.append("The client hasn't approved the work yet (or the 5 business days haven't passed).")
    if session.exec(select(Claim).where(Claim.invoice_id == invoice.id,
                                        Claim.status.in_(["submitted", "ai_reviewed", "paid"]))).first():
        blocks.append("There's a claim on this invoice. The pool can't cover it twice.")
    if active(select(Advance).where(Advance.invoice_id == invoice.id, Advance.status.in_(ACTIVE))):
        blocks.append("This invoice already has an advance.")

    # The client
    facts = client_history(session, job)
    level = risk_level(facts)
    if level == "high":
        blocks.append(f"{job.client_name} is high risk: an unpaid invoice is over 14 days old or the pool already covered them.")

    # The member
    if not pledge_signed(session, member):
        blocks.append("Sign the Member Pledge on your profile first.")
    if not member.paypal_email:
        blocks.append("Add a PayPal email on your profile first.")
    paid_before = session.exec(
        select(Invoice).join(Milestone).join(Job)
        .where(Job.guild_id == guild.id, Job.worker_id == member.id, Invoice.status == "paid")
    ).first()
    if not paid_before:
        blocks.append("You need one paid invoice with the guild before you can be paid early.")
    if session.exec(select(MemberDebt).where(MemberDebt.member_id == member.id, MemberDebt.status == "open")).first():
        blocks.append("You owe the guild money. That has to be paid back first.")
    if session.exec(select(Advance).where(Advance.member_id == member.id, Advance.status == "defaulted")).first():
        blocks.append("A past advance wasn't paid back on time.")
    others = active(select(Advance).where(Advance.member_id == member.id, Advance.status.in_(ACTIVE),
                                          Advance.invoice_id != invoice.id))
    if others:
        blocks.append("You already have an advance open. One at a time.")

    # The pool
    limit = guild.pool_balance * POOL_SHARE_LIMIT // 100
    if a["advance_cents"] <= 0:
        blocks.append("This invoice is too small to pay early.")
    elif a["advance_cents"] > limit:
        blocks.append(
            f"The pool has {money(guild.pool_balance)}. One advance can use at most half, "
            f"{money(limit)}, and this one needs {money(a['advance_cents'])}."
        )

    return {
        "eligible": not blocks,
        "blocks": blocks,
        **a,
        "pool_cents": guild.pool_balance,
        "pool_after_cents": guild.pool_balance - a["advance_cents"],
        "client": job.client_name,
        "client_risk": level,
        "client_facts": facts,
        "repay_days": REPAY_DAYS,
    }


def _rules_note(member: Member, c: dict) -> str:
    return (
        f"{member.name} gets {money(c['advance_cents'])} now and the pool takes back {money(c['repay_cents'])} "
        f"when {c['client']} pays the {money(c['invoice_cents'])} invoice. "
        f"The client is {c['client_risk']} risk and the pool keeps {money(c['pool_after_cents'])}."
    )


def _ai_note(member: Member, c: dict) -> tuple[str, str]:
    f = c["client_facts"]
    facts = "\n".join([
        f"- Member: {member.name}",
        f"- Client: {c['client']}, risk level {c['client_risk']}",
        f"- Client record: {f['invoices_sent']} invoices sent, {f['invoices_paid']} paid, "
        f"{f['invoices_unpaid']} unpaid, oldest unpaid {f['longest_unpaid_days']} days, "
        f"{f['reminders_sent']} reminders sent",
        f"- Invoice: {money(c['invoice_cents'])}",
        f"- Paid now: {money(c['advance_cents'])}",
        f"- Fee: {money(c['fee_cents'])}",
        f"- Pool takes back when the client pays: {money(c['repay_cents'])}",
        f"- Member still gets later: {money(c['later_cents'])}",
        f"- Pool now: {money(c['pool_cents'])}, after this: {money(c['pool_after_cents'])}",
        f"- If unpaid after {REPAY_DAYS} days, the member owes it back from future payouts",
    ])
    try:
        out = run_ai_json(
            [{"role": "system", "content": ADVANCE_NOTE}, {"role": "user", "content": f"FACTS\n{facts}"}],
            schema=Note, temperature=0.2, max_tokens=200, feature="advance",
        )
        # Code checks the AI: every dollar amount must be one we gave it.
        allowed = {money(c[k]) for k in ("invoice_cents", "advance_cents", "fee_cents", "repay_cents",
                                         "later_cents", "pool_cents", "pool_after_cents")}
        said = set(re.findall(r"\$[\d,]+\.\d{2}", out.note))
        if said - allowed or "{" in out.note:
            logger.warning("Advance note had amounts we didn't give it: %s", said - allowed)
        else:
            return out.note.strip(), "ai"
    except AIError as e:
        logger.info("Advance note fell back to rules: %s", e)
    return _rules_note(member, c), "rules"


# ---------------------------------------------------------------- request, approve, decline

def request(session: Session, invoice: Invoice, member: Member) -> Advance:
    c = check(session, invoice, member)
    if not c["eligible"]:
        raise ValueError(c["blocks"][0])
    note, by = _ai_note(member, c)
    ms, job, guild = _context(session, invoice)
    adv = Advance(guild_id=guild.id, invoice_id=invoice.id, member_id=member.id,
                  advance_cents=c["advance_cents"], fee_cents=c["fee_cents"], explanation=note, explained_by=by)
    session.add(adv)
    session.flush()
    session.add(AgentAction(
        guild_id=guild.id,
        action="advance.requested",
        inputs={"by": member.name, "job_id": str(job.id), "invoice_id": str(invoice.id), "advance_id": str(adv.id)},
        result={"client": job.client_name, "advance_cents": adv.advance_cents, "fee_cents": adv.fee_cents,
                "note": note, "written_by": by},
    ))
    return adv


def approve(session: Session, adv: Advance, admin: Member) -> dict:
    """Pay the advance. PayPal errors are raised so the caller rolls back. Callers commit."""
    adv = session.exec(select(Advance).where(Advance.id == adv.id).with_for_update()).one()
    if adv.status != "pending":
        raise ValueError(f"This advance is already {adv.status}")
    if adv.member_id == admin.id:
        raise PermissionError("Another admin has to approve your own advance")

    invoice = session.get(Invoice, adv.invoice_id)
    member = session.get(Member, adv.member_id)
    # Things may have changed since the request (client paid, a claim, the pool moved). Check again.
    c = check(session, invoice, member, ignore=adv)
    if not c["eligible"]:
        raise ValueError(f"Can't pay it now: {c['blocks'][0]}")

    ms, job, _ = _context(session, invoice)
    guild = session.exec(select(Guild).where(Guild.id == job.guild_id).with_for_update()).one()
    payout = Payout(guild_id=guild.id, source_type="advance", source_id=adv.id, member_id=member.id,
                    amount=adv.advance_cents, kind="advance")
    session.add(payout)
    session.flush()
    batch_id = paypal_payouts.send_batch_payout(
        [{"receiver_email": member.paypal_email, "amount_cents": adv.advance_cents,
          "note": f"Paid early by the guild for {job.client_name}: {ms.title}", "item_id": str(payout.id)}],
        batch_ref=f"ADV-{adv.id}",
    )
    payout.paypal_batch_id, payout.status = batch_id, "sent"
    guild.pool_balance -= adv.advance_cents
    session.add(PoolTx(guild_id=guild.id, amount=adv.advance_cents, direction="out", source="advance_paid",
                       external_ref=f"advance:{adv.id}"))
    adv.status, adv.paid_at, adv.decided_by, adv.paypal_batch_id = "paid", utcnow(), admin.name, batch_id
    session.add_all([payout, guild, adv])
    session.add(AgentAction(
        guild_id=guild.id,
        action="advance.paid",
        inputs={"by": admin.name, "member": member.name, "job_id": str(job.id), "invoice_id": str(invoice.id),
                "advance_id": str(adv.id)},
        result={"client": job.client_name, "advance_cents": adv.advance_cents, "pool_after": guild.pool_balance,
                "batch_id": batch_id},
    ))
    return {"status": "paid", "advance_cents": adv.advance_cents, "pool_after_cents": guild.pool_balance,
            "batch_id": batch_id}


def decline(session: Session, adv: Advance, admin: Member, note: str) -> None:
    if adv.status != "pending":
        raise ValueError(f"This advance is already {adv.status}")
    adv.status, adv.decided_by, adv.decision_note, adv.closed_at = "declined", admin.name, note.strip()[:500], utcnow()
    session.add(adv)
    session.add(AgentAction(
        guild_id=adv.guild_id,
        action="advance.declined",
        inputs={"by": admin.name, "invoice_id": str(adv.invoice_id), "advance_id": str(adv.id)},
        result={"note": adv.decision_note},
    ))


# ---------------------------------------------------------------- hooks used by other services

def blocks_claim(session: Session, invoice_id) -> bool:
    return session.exec(
        select(Advance).where(Advance.invoice_id == invoice_id, Advance.status.in_(BLOCKS_CLAIM))
    ).first() is not None


def take_back(session: Session, guild: Guild, invoice: Invoice, job: Job, worker_cents: int) -> int:
    """Called from money.py before payouts. Returns the cents taken from the worker's share.

    The caller has the guild row locked.
    """
    for pending in session.exec(
        select(Advance).where(Advance.invoice_id == invoice.id, Advance.status == "pending")
    ).all():
        pending.status, pending.decision_note, pending.closed_at = "declined", "The client paid first.", utcnow()
        session.add(pending)

    adv = session.exec(select(Advance).where(Advance.invoice_id == invoice.id, Advance.status == "paid")).first()
    if not adv:
        return 0
    owed = adv.advance_cents + adv.fee_cents
    taken = min(owed, worker_cents)
    back, fee = min(taken, adv.advance_cents), max(0, taken - adv.advance_cents)
    guild.pool_balance += taken
    session.add(PoolTx(guild_id=guild.id, amount=back, direction="in", source="advance_repaid",
                       external_ref=f"advance_repaid:{adv.id}"))
    if fee:
        session.add(PoolTx(guild_id=guild.id, amount=fee, direction="in", source="advance_fee",
                           external_ref=f"advance_fee:{adv.id}"))
    adv.status, adv.closed_at = "repaid", utcnow()
    if taken < owed:   # can't happen with the cap in amounts(), but never lose track of money
        debt = MemberDebt(guild_id=guild.id, member_id=adv.member_id, kind="advance", source_id=str(adv.id),
                          amount_cents=owed - taken, note=f"Rest of the advance for {job.client_name}")
        session.add(debt)
        session.flush()
        adv.member_debt_id = debt.id
    session.add(adv)
    session.add(AgentAction(
        guild_id=guild.id,
        action="advance.repaid",
        inputs={"job_id": str(job.id), "invoice_id": str(invoice.id), "advance_id": str(adv.id)},
        result={"client": job.client_name, "advance_cents": adv.advance_cents, "fee_cents": adv.fee_cents,
                "taken_cents": taken},
    ))
    return taken


def owed_on_direct(session: Session, invoice_id) -> Advance | None:
    """The paid advance on an invoice the client paid to the member directly (12A)."""
    for pending in session.exec(
        select(Advance).where(Advance.invoice_id == invoice_id, Advance.status == "pending")
    ).all():
        pending.status, pending.decision_note, pending.closed_at = "declined", "The client paid the member directly.", utcnow()
        session.add(pending)
    return session.exec(select(Advance).where(Advance.invoice_id == invoice_id, Advance.status == "paid")).first()


# ---------------------------------------------------------------- the 45-day sweep

def sweep_defaults(session: Session) -> list[dict]:
    """Daily cron. Advances still unpaid 45 days later become a debt. Commits."""
    cutoff = utcnow() - timedelta(days=REPAY_DAYS)
    done = []
    for adv in session.exec(select(Advance).where(Advance.status == "paid")).all():
        paid_at = adv.paid_at if adv.paid_at.tzinfo else adv.paid_at.replace(tzinfo=cutoff.tzinfo)
        if paid_at > cutoff:
            continue
        invoice = session.get(Invoice, adv.invoice_id)
        if invoice.status != "sent":
            continue   # paid or cancelled. money.py or 12A already handled it.
        ms, job, _ = _context(session, invoice)
        member = session.get(Member, adv.member_id)
        debt = MemberDebt(guild_id=adv.guild_id, member_id=adv.member_id, kind="advance", source_id=str(adv.id),
                          amount_cents=adv.advance_cents + adv.fee_cents,
                          note=f"Advance for {job.client_name}: {ms.title}. Not paid in {REPAY_DAYS} days.")
        session.add(debt)
        session.flush()
        adv.status, adv.closed_at, adv.member_debt_id = "defaulted", utcnow(), debt.id
        session.add(adv)
        session.add(AgentAction(
            guild_id=adv.guild_id,
            action="advance.defaulted",
            inputs={"member": member.name, "job_id": str(job.id), "invoice_id": str(invoice.id),
                    "advance_id": str(adv.id)},
            result={"client": job.client_name, "owed_cents": debt.amount_cents, "days": REPAY_DAYS},
        ))
        done.append({"advance_id": str(adv.id), "member": member.name, "client": job.client_name,
                     "owed_cents": debt.amount_cents})
    session.commit()
    return done


# ---------------------------------------------------------------- lists

def overview(session: Session, me: Member) -> dict:
    is_admin = me.role == "admin"
    q = select(Advance).where(Advance.guild_id == me.guild_id).order_by(Advance.created_at.desc())
    rows = session.exec(q).all()
    if not is_admin:
        rows = [a for a in rows if a.member_id == me.id]
    names = {m.id: m.name for m in session.exec(select(Member).where(Member.guild_id == me.guild_id)).all()}
    out = []
    for a in rows:
        invoice = session.get(Invoice, a.invoice_id)
        ms, job, _ = _context(session, invoice)
        row = {
            "id": str(a.id), "member": names.get(a.member_id, ""), "is_me": a.member_id == me.id,
            "job_id": str(job.id), "client": job.client_name, "milestone": ms.title,
            "invoice_cents": invoice.amount, "advance_cents": a.advance_cents, "fee_cents": a.fee_cents,
            "status": a.status, "explanation": a.explanation, "explained_by": a.explained_by,
            "decided_by": a.decided_by, "decision_note": a.decision_note,
            "created_at": a.created_at.isoformat(),
            "paid_at": a.paid_at.isoformat() if a.paid_at else None,
            "due_at": (a.paid_at + timedelta(days=REPAY_DAYS)).isoformat() if a.paid_at else None,
            "blocks": [],
        }
        if a.status == "pending" and is_admin:
            row["blocks"] = check(session, invoice, session.get(Member, a.member_id), ignore=a)["blocks"]
        out.append(row)
    return {"advances": out, "pending": sum(1 for r in out if r["status"] == "pending")}
