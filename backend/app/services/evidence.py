"""Evidence pack: everything recorded about one job, in one place.

Used for claims, PayPal disputes, or just to show a client what happened.
Facts only, straight from the database. No AI.
Each agreement's hash is checked again here, so a changed text shows as "does not match".
"""
from sqlmodel import Session, select

from app.models import (
    AgentAction, Agreement, Claim, Deposit, Guild, Invoice, Job, Member, Milestone, Payout, Reminder, utcnow,
)
from app.services.agreements import sha256


def _iso(dt):
    return dt.isoformat() if dt else None


def build_evidence(session: Session, job: Job) -> dict:
    guild = session.get(Guild, job.guild_id)
    worker = session.get(Member, job.worker_id) if job.worker_id else None
    referrer = session.get(Member, job.referrer_id) if job.referrer_id else None

    ms = session.exec(
        select(Milestone).where(Milestone.job_id == job.id).order_by(Milestone.created_at, Milestone.id)
    ).all()
    ms_ids = [m.id for m in ms]
    invoices = session.exec(select(Invoice).where(Invoice.milestone_id.in_(ms_ids))).all() if ms_ids else []
    deposits = session.exec(select(Deposit).where(Deposit.milestone_id.in_(ms_ids))).all() if ms_ids else []
    inv_ids = [i.id for i in invoices]
    reminders = session.exec(select(Reminder).where(Reminder.invoice_id.in_(inv_ids))).all() if inv_ids else []
    claims = session.exec(select(Claim).where(Claim.invoice_id.in_(inv_ids))).all() if inv_ids else []
    claim_ids = [c.id for c in claims]
    payouts = session.exec(
        select(Payout).where(Payout.source_id.in_(inv_ids + claim_ids))
    ).all() if (inv_ids or claim_ids) else []
    agreements = session.exec(
        select(Agreement).where(Agreement.job_id == job.id).order_by(Agreement.accepted_at)
    ).all()

    # Timeline: every log entry that points at this job, its invoices, deposits or claims.
    keys = {str(job.id)} | {str(x) for x in inv_ids} | {str(d.id) for d in deposits} | {str(x) for x in claim_ids}
    timeline = []
    for a in session.exec(
        select(AgentAction).where(AgentAction.guild_id == job.guild_id).order_by(AgentAction.created_at)
    ).all():
        i = a.inputs or {}
        if {str(i.get(k)) for k in ("job_id", "invoice_id", "deposit_id", "claim_id") if i.get(k)} & keys:
            timeline.append({"at": _iso(a.created_at), "action": a.action, "inputs": i, "result": a.result or {}})

    def milestone_out(m: Milestone) -> dict:
        inv = [i for i in invoices if i.milestone_id == m.id]
        return {
            "title": m.title,
            "scope": m.scope,
            "amount_cents": m.amount,
            "status": m.status,
            "created_at": _iso(m.created_at),
            "delivered_at": _iso(m.delivered_at),
            "delivery_note": m.delivery_note,
            "approved_at": _iso(m.client_approved_at),
            "approved_by": m.approved_by,
            "changes_requested_at": _iso(m.client_changes_requested_at),
            "client_feedback": m.client_feedback,
            "invoices": [
                {"paypal_invoice_id": i.paypal_invoice_id, "amount_cents": i.amount, "status": i.status,
                 "sent_at": _iso(i.sent_at), "paid_at": _iso(i.paid_at),
                 "reminders": [{"tier": r.tier, "sent_at": _iso(r.sent_at), "subject": r.subject,
                                "days_overdue": r.days_overdue}
                               for r in sorted((r for r in reminders if r.invoice_id == i.id), key=lambda r: r.tier)]}
                for i in inv
            ],
            "deposits": [
                {"status": d.status, "amount_cents": d.amount_cents, "paypal_order_id": d.paypal_order_id,
                 "paypal_authorization_id": d.paypal_authorization_id, "paypal_capture_id": d.paypal_capture_id,
                 "authorized_at": _iso(d.authorized_at), "captured_at": _iso(d.captured_at),
                 "voided_at": _iso(d.voided_at)}
                for d in deposits if d.milestone_id == m.id
            ],
        }

    names = {m.id: m.name for m in session.exec(select(Member).where(Member.guild_id == job.guild_id)).all()}
    return {
        "generated_at": _iso(utcnow()),
        "guild": guild.name if guild else "",
        "job": {
            "id": str(job.id),
            "client_name": job.client_name,
            "client_email": job.client_email,
            "description": job.description,
            "status": job.status,
            "created_at": _iso(job.created_at),
            "worker": worker.name if worker else "",
            "referrer": referrer.name if referrer else "",
        },
        "agreements": [
            {"kind": a.kind, "template": a.template_version, "signer": a.signer_name, "email": a.signer_email,
             "accepted_at": _iso(a.accepted_at), "ip": a.ip, "sha256": a.sha256,
             "hash_matches": sha256(a.body) == a.sha256, "milestones": len(a.milestone_ids or []),
             "total_cents": a.total_cents, "body": a.body}
            for a in agreements
        ],
        "milestones": [milestone_out(m) for m in ms],
        "payouts": [
            {"to": names.get(p.member_id, ""), "kind": p.kind, "amount_cents": p.amount, "status": p.status,
             "paypal_batch_id": p.paypal_batch_id, "at": _iso(p.created_at)}
            for p in sorted(payouts, key=lambda p: p.created_at)
        ],
        "claims": [
            {"status": c.status, "filed_at": _iso(c.created_at), "by": names.get(c.member_id, ""),
             "ai_verdict": c.ai_verdict, "ai_confidence": c.ai_confidence, "admin_decision": c.admin_decision,
             "admin_note": c.admin_note}
            for c in claims
        ],
        "timeline": timeline,
    }
