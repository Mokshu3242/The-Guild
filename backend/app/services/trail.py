"""14A Money trail: every step one invoice's money took, in order, with the real PayPal IDs.

Facts only, no AI. Amounts come from the rows and from the split the money code logged
when it ran (invoice.paid.split), so the trail shows exactly what happened, not a guess.
"""
from datetime import timezone

from sqlmodel import Session, select

from app.models import (
    Advance, AgentAction, Claim, Deposit, DirectPayment, Invoice, Job, Member, MemberDebt, Milestone, Payout,
    Reminder,
)
from app.services.advances import REPAY_DAYS as REPAY


def _iso(dt) -> str | None:
    if not dt:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat()


def money(c: int) -> str:
    return f"${c // 100:,}.{c % 100:02d}"


def build_trail(session: Session, invoice: Invoice) -> dict:
    ms = session.get(Milestone, invoice.milestone_id)
    job = session.get(Job, ms.job_id)
    names = {m.id: m.name for m in session.exec(select(Member).where(Member.guild_id == job.guild_id)).all()}
    who = lambda mid: names.get(mid, "a member")  # noqa: E731

    ev: list[dict] = []

    def add(at, kind, title, detail="", ids=None, amount=0, flow="info"):
        if at:
            ev.append({"at": _iso(at), "kind": kind, "title": title, "detail": detail,
                       "ids": [i for i in (ids or []) if i[1]], "amount_cents": amount, "flow": flow})

    # Deposit hold (5D). A captured deposit becomes an invoice named DEPOSIT-<order id>.
    for d in session.exec(select(Deposit).where(Deposit.milestone_id == ms.id).order_by(Deposit.created_at)).all():
        if invoice.paypal_invoice_id.startswith("DEPOSIT-") and d.paypal_order_id not in invoice.paypal_invoice_id:
            continue
        ids = [("PayPal order", d.paypal_order_id), ("Authorization", d.paypal_authorization_id)]
        add(d.authorized_at, "deposit", f"{job.client_name} approved a deposit hold", "The money is held, not taken yet.",
            ids, d.amount_cents, "hold")
        add(d.captured_at, "deposit", "Deposit captured", "The held money was taken after delivery.",
            [("Capture", d.paypal_capture_id)], d.amount_cents, "in")
        add(d.voided_at, "deposit", "Deposit hold released", "Nothing was charged.", [], d.amount_cents, "info")

    if not invoice.paypal_invoice_id.startswith("DEPOSIT-"):
        add(invoice.sent_at, "invoice", f"Invoice sent to {job.client_name}", ms.title,
            [("PayPal invoice", invoice.paypal_invoice_id)], invoice.amount, "expect")

    for r in session.exec(select(Reminder).where(Reminder.invoice_id == invoice.id).order_by(Reminder.tier)).all():
        add(r.sent_at, "reminder", f"Reminder {r.tier} of 3 sent through PayPal",
            f'"{r.subject}" ({r.days_overdue} days after sending, written by {"the AI" if r.written_by == "ai" else "a template"})')

    # Claims (pool covers the worker)
    claims = session.exec(select(Claim).where(Claim.invoice_id == invoice.id).order_by(Claim.created_at)).all()
    for c in claims:
        verdict = f"AI said {c.ai_verdict.replace('_', ' ')}, {round((c.ai_confidence or 0) * 100)}% sure." if c.ai_verdict else ""
        add(c.created_at, "claim", f"{who(c.member_id)} filed a claim", verdict)
        if c.status == "rejected":
            log = next((x for x in session.exec(select(AgentAction).where(
                AgentAction.guild_id == job.guild_id, AgentAction.action == "claim.rejected")).all()
                if (x.inputs or {}).get("claim_id") == str(c.id)), None)
            add(log.created_at if log else c.created_at, "claim", "Claim rejected", c.admin_note)

    # Advances (pool pays the worker early)
    advances = session.exec(select(Advance).where(Advance.invoice_id == invoice.id).order_by(Advance.created_at)).all()
    for a in advances:
        if a.status == "declined":
            continue
        add(a.closed_at if a.status == "defaulted" else None, "advance",
            f"{REPAY} days passed without payment", f"{who(a.member_id)} now owes the guild "
            f"{money(a.advance_cents + a.fee_cents)}, taken from their next payouts.")
        add(a.closed_at if a.status == "converted" else None, "advance", "Advance moved into what the member owes",
            "The client paid the member directly, so the advance became part of that debt.")

    # Direct payment (client paid the member outside PayPal)
    for dp in session.exec(select(DirectPayment).where(DirectPayment.invoice_id == invoice.id)).all():
        add(dp.created_at, "direct", f"{who(dp.member_id)} said the client paid them directly",
            f"{money(dp.amount_cents)} by {dp.method}.")
        if dp.status == "settled":
            add(dp.decided_at, "direct", f"{dp.decided_by} closed the invoice as paid directly",
                f"Nothing was split. {who(dp.member_id)} owes the guild {money(dp.owed_cents)}.", [], dp.owed_cents, "owed")
        elif dp.status == "rejected":
            add(dp.decided_at, "direct", f"{dp.decided_by} rejected the report", dp.decision_note)

    # The client paid through PayPal, and the money code split it
    split = None
    for a in session.exec(select(AgentAction).where(
            AgentAction.guild_id == job.guild_id, AgentAction.action == "invoice.paid.split")).all():
        if (a.inputs or {}).get("invoice_id") == str(invoice.id):
            split = a
    paid_direct = any(dp.status == "settled" for dp in session.exec(
        select(DirectPayment).where(DirectPayment.invoice_id == invoice.id)).all())
    if invoice.paid_at and not paid_direct and not invoice.paypal_invoice_id.startswith("DEPOSIT-"):
        add(invoice.paid_at, "payment", f"{job.client_name} paid the invoice", "Through PayPal.",
            [("PayPal invoice", invoice.paypal_invoice_id)], invoice.amount, "in")
    if split:
        r = split.result or {}
        parts = [f"{money(r.get('worker_cents', 0))} to the worker"]
        if r.get("referrer_cents"):
            parts.append(f"{money(r['referrer_cents'])} to the referrer")
        parts.append(f"{money(r.get('pool_cents', 0))} to the pool")
        if r.get("recovered_cents"):
            parts.append(f"{money(r['recovered_cents'])} back to the pool for the claim it paid")
        if r.get("advance_back_cents"):
            parts.append(f"{money(r['advance_back_cents'])} back to the pool for the advance and its fee")
        if r.get("set_off_cents"):
            parts.append(f"{money(r['set_off_cents'])} to the pool for money a member owed")
        add(split.created_at, "split", "Split by the rules", ", ".join(parts) + ".")

    # Every payout tied to this invoice, its claims or its advances
    sources = [invoice.id] + [c.id for c in claims] + [a.id for a in advances]
    for p in session.exec(select(Payout).where(Payout.source_id.in_(sources)).order_by(Payout.created_at)).all():
        label = {"work": "Work payout to {}", "referral": "Referral fee to {}",
                 "claim": "Safety pool covered {}'s claim", "advance": "Paid {} early from the pool"}.get(
            p.kind, p.kind.title() + " to {}")
        if p.status == "paid_direct":
            add(p.created_at, "payout", f"{who(p.member_id)} kept their share", "Already paid by the client directly.",
                [], p.amount, "info")
            continue
        add(p.created_at, "payout", label.format(who(p.member_id)), f"PayPal Payouts, {p.status.replace('_', ' ')}.",
            [("Payout batch", p.paypal_batch_id)], p.amount, "out")

    # Debts this invoice created
    debt_sources = [str(x) for x in [a.id for a in advances]]
    debt_sources += [str(dp.id) for dp in session.exec(select(DirectPayment).where(DirectPayment.invoice_id == invoice.id)).all()]
    for d in session.exec(select(MemberDebt).where(MemberDebt.source_id.in_(debt_sources))).all() if debt_sources else []:
        if d.status == "repaid":
            add(d.closed_at, "debt", f"{who(d.member_id)} paid back {money(d.amount_cents)}",
                "Taken from their later payouts, into the pool.", [], d.amount_cents, "in")
        elif d.status == "written_off":
            add(d.closed_at, "debt", "An admin wrote off the rest", d.note, [], d.amount_cents - d.repaid_cents, "info")

    # Payouts are created a moment before the invoice is marked paid, in the same step.
    # Sort by the second, then by the order the money actually moves.
    rank = {"deposit": 0, "invoice": 1, "reminder": 2, "claim": 3, "direct": 4, "payment": 5, "split": 6,
            "payout": 7, "advance": 8, "debt": 9}
    ev.sort(key=lambda e: (e["at"][:19], rank.get(e["kind"], 5)))

    # The bottom line, from the split (or the direct settlement)
    summary = None
    if split:
        r = split.result or {}
        summary = {
            "client_paid_cents": invoice.amount,
            "worker_cents": r.get("worker_cents", 0),
            "referrer_cents": r.get("referrer_cents", 0),
            "pool_cents": r.get("pool_cents", 0) + r.get("recovered_cents", 0) + r.get("advance_back_cents", 0)
                          + r.get("set_off_cents", 0),
        }
    worker = session.get(Member, job.worker_id) if job.worker_id else None
    referrer = session.get(Member, job.referrer_id) if job.referrer_id else None
    return {
        "invoice_id": str(invoice.id),
        "job_id": str(job.id),
        "paypal_invoice_id": invoice.paypal_invoice_id,
        "amount_cents": invoice.amount,
        "status": "paid directly" if paid_direct else invoice.status,
        "client": job.client_name,
        "milestone": ms.title,
        "worker": worker.name if worker else "",
        "referrer": referrer.name if referrer else "",
        "summary": summary,
        "events": ev,
    }

