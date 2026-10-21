"""Client portal: a no-login page per job, opened with a secret link.

The token is the only credential, like a shared document link. Rotating it kills the old link.
Clients can look, approve delivered work, and ask for changes. Nothing else.
Paying stays on PayPal's own pages.
"""
import logging
import secrets

from fastapi import HTTPException
from sqlmodel import Session, select

from app.config import settings
from app.db import engine
from app.models import AgentAction, Deposit, Guild, Invoice, Job, Member, Milestone, utcnow
from app.services.agreements import work_state
from app.services.notices import active_maintenance

logger = logging.getLogger(__name__)

DONE_JOB = ("paid",)                      # nothing left to review
LOCKED_MS = ("paid", "covered")           # milestone statuses the client can't act on
DEAD_DEPOSIT = ("captured", "voided", "released", "cancelled", "expired")


# ---------- Tokens ----------

def new_token() -> str:
    return secrets.token_urlsafe(24)


def ensure_token(job: Job) -> str:
    """Create a link if the job has none. The caller adds and commits the job."""
    if not job.portal_token:
        job.portal_token = new_token()
        job.portal_token_created_at = utcnow()
    return job.portal_token


def portal_path(job: Job) -> str:
    return f"/portal/?t={job.portal_token}" if job.portal_token else ""


def portal_url(job: Job) -> str:
    base = (getattr(settings, "frontend_url", "") or "").rstrip("/")
    return f"{base}{portal_path(job)}" if base and job.portal_token else ""


def job_by_token(session: Session, token: str) -> Job:
    if not token or len(token) < 20 or len(token) > 64:
        raise HTTPException(404, "This link is not active")
    job = session.exec(select(Job).where(Job.portal_token == token)).first()
    if not job:
        raise HTTPException(404, "This link is not active")
    return job


def block_writes_if_paused(session: Session, job: Job) -> None:
    """Maintenance or a suspended guild stops client actions. Viewing still works."""
    w = active_maintenance(session, job.guild_id)
    if w:
        raise HTTPException(503, "The guild is paused for a short while. Please try again later.")


# ---------- Shared helpers ----------

def _milestones(session: Session, job: Job) -> list[Milestone]:
    order = getattr(Milestone, "created_at", None)
    q = select(Milestone).where(Milestone.job_id == job.id)
    return session.exec(q.order_by(order) if order is not None else q).all()


def _latest_by_ms(rows) -> dict:
    out: dict = {}
    for r in rows:
        prev = out.get(r.milestone_id)
        if prev is None or (getattr(r, "created_at", None) and r.created_at > prev.created_at):
            out[r.milestone_id] = r
    return out


def _changes_open(m: Milestone) -> bool:
    asked = m.client_changes_requested_at
    return bool(asked and (not m.delivered_at or asked > m.delivered_at))


def _days(dt) -> int:
    return max(0, (utcnow() - dt).days) if dt else 0


def stage(m: Milestone, inv: Invoice | None) -> str:
    """One plain word the client understands. Order matters."""
    if (inv and inv.status == "paid") or m.status == "paid":
        return "paid"
    if inv and inv.status == "sent":
        return "payment_due"
    if _changes_open(m):
        return "changes_requested"
    if m.client_approved_at:
        return "approved"
    if m.delivered_at:
        return "review"
    return "in_progress"


def can_review(m: Milestone, inv: Invoice | None) -> bool:
    """Client can approve once work is delivered (or invoiced), until it's paid."""
    if m.status in LOCKED_MS or (inv and inv.status == "paid"):
        return False
    if m.client_approved_at or _changes_open(m):
        return False
    return bool(m.delivered_at or (inv and inv.status == "sent"))


def can_change(m: Milestone, inv: Invoice | None) -> bool:
    """Asking for changes only makes sense before the bill goes out. After that, approve or talk to the guild."""
    return can_review(m, inv) and not (inv and inv.status == "sent")


def _deposit_out(d: Deposit | None) -> dict | None:
    if not d or d.status in DEAD_DEPOSIT:
        return None
    amount = getattr(d, "amount_cents", None) or getattr(d, "amount", 0) or 0
    on_hold = d.status in ("authorized", "held") or bool(getattr(d, "authorization_id", None))
    return {
        "state": "on_hold" if on_hold else "needs_approval",
        "amount_cents": int(amount),
        "approve_url": "" if on_hold else (getattr(d, "approve_url", "") or ""),
    }


def _invoice_out(inv: Invoice | None) -> dict | None:
    if not inv:
        return None
    return {
        "status": inv.status,
        "pay_url": getattr(inv, "pay_url", "") or "",
        "days_open": _days(inv.sent_at) if inv.status == "sent" else 0,
    }


# ---------- Client side ----------

def portal_view(session: Session, job: Job) -> dict:
    guild = session.get(Guild, job.guild_id)
    worker = session.get(Member, job.worker_id) if job.worker_id else None
    ms = _milestones(session, job)
    ids = [m.id for m in ms]
    invs = _latest_by_ms(session.exec(select(Invoice).where(Invoice.milestone_id.in_(ids))).all()) if ids else {}
    deps = _latest_by_ms(session.exec(select(Deposit).where(Deposit.milestone_id.in_(ids))).all()) if ids else {}

    agreement = work_state(session, job)
    signed = set(agreement.pop("signed_ids"))

    rows = []
    for m in ms:
        inv = invs.get(m.id)
        rows.append({
            "id": str(m.id),
            "title": m.title,
            "scope": m.scope,
            "amount_cents": m.amount,
            "stage": stage(m, inv),
            "can_review": can_review(m, inv),
            "can_change": can_change(m, inv),
            "in_agreement": str(m.id) in signed,
            "delivered_at": m.delivered_at.isoformat() if m.delivered_at else None,
            "delivery_note": m.delivery_note,
            "approved_at": m.client_approved_at.isoformat() if m.client_approved_at else None,
            "feedback": m.client_feedback if _changes_open(m) else "",
            "invoice": _invoice_out(inv),
            "deposit": _deposit_out(deps.get(m.id)),
        })

    total = sum(m.amount for m in ms)
    paid = sum(r["amount_cents"] for r in rows if r["stage"] == "paid")
    return {
        "guild_name": guild.name if guild else "The Guild",
        "client_name": job.client_name,
        "worker_name": worker.name if worker else "",
        "description": job.description,
        "total_cents": total,
        "paid_cents": paid,
        "client_email": job.client_email,
        "agreement": agreement,
        "milestones": rows,
    }


def _ms_for_client(session: Session, job: Job, milestone_id, changes: bool = False) -> tuple[Milestone, Invoice | None]:
    m = session.get(Milestone, milestone_id)
    if not m or m.job_id != job.id:
        raise HTTPException(404, "Milestone not found")
    inv = _latest_by_ms(session.exec(select(Invoice).where(Invoice.milestone_id == m.id)).all()).get(m.id)
    allowed = can_change(m, inv) if changes else can_review(m, inv)
    if not allowed:
        if changes and inv and inv.status == "sent":
            raise HTTPException(409, "This milestone is already invoiced. You can still approve it, or reply to the invoice email.")
        raise HTTPException(409, "This milestone isn't waiting for your review right now")
    return m, inv


def client_approve(session: Session, job: Job, milestone_id) -> None:
    m, _ = _ms_for_client(session, job, milestone_id)
    m.client_approved_at = utcnow()
    session.add(m)
    session.add(AgentAction(
        guild_id=job.guild_id,
        action="portal.client_approved",
        inputs={"job_id": str(job.id), "milestone_id": str(m.id), "by": job.client_name},
        result={"milestone": m.title},
    ))


def client_request_changes(session: Session, job: Job, milestone_id, feedback: str) -> None:
    m, _ = _ms_for_client(session, job, milestone_id, changes=True)
    m.client_changes_requested_at = utcnow()
    m.client_feedback = feedback.strip()[:1500]
    session.add(m)
    session.add(AgentAction(
        guild_id=job.guild_id,
        action="portal.client_changes",
        inputs={"job_id": str(job.id), "milestone_id": str(m.id), "by": job.client_name},
        result={"milestone": m.title, "feedback": m.client_feedback[:200]},
    ))


def scope_check_in_background(job_id, feedback: str) -> None:
    """Runs after the response is sent, so the client never waits on the AI.

    Uses the job's worker (or poster) as the member, because check_creep needs one.
    If the AI is off or fails, the client's request is still saved. Members can run the check by hand.
    """
    from app.services.scope_creep import check_creep   # local import keeps startup light

    with Session(engine) as s:
        try:
            job = s.get(Job, job_id)
            if not job or job.status not in ("open", "matched", "in_progress"):
                return
            member = s.get(Member, job.worker_id or job.referrer_id)
            if not member:
                return
            check_creep(s, job, member, feedback)
            s.commit()
        except Exception as e:   # AIError, kill switch, anything: never break the portal
            s.rollback()
            logger.info("Portal scope check skipped for job %s: %s", job_id, type(e).__name__)


# ---------- Member side ----------

def can_manage(job: Job, me: Member) -> bool:
    return me.role == "admin" or me.id in (job.referrer_id, job.worker_id)


def member_view(session: Session, job: Job, me: Member) -> dict:
    ms = _milestones(session, job)
    ids = [m.id for m in ms]
    invs = _latest_by_ms(session.exec(select(Invoice).where(Invoice.milestone_id.in_(ids))).all()) if ids else {}
    agreement = work_state(session, job)
    signed = set(agreement["signed_ids"])
    return {
        "agreement": {
            "needs_signature": agreement["needs_signature"],
            "new_titles": agreement["new_titles"],
            "signed": agreement["signed"],
        },
        "enabled": bool(job.portal_token),
        "path": portal_path(job) if can_manage(job, me) else "",
        "created_at": job.portal_token_created_at.isoformat() if job.portal_token_created_at else None,
        "can_manage": can_manage(job, me),
        "can_deliver": me.role == "admin" or me.id == job.worker_id,
        "milestones": [
            {
                "id": str(m.id),
                "title": m.title,
                "stage": stage(m, invs.get(m.id)),
                "delivered_at": m.delivered_at.isoformat() if m.delivered_at else None,
                "approved_at": m.client_approved_at.isoformat() if m.client_approved_at else None,
                "feedback": m.client_feedback if _changes_open(m) else "",
                "locked": m.status in LOCKED_MS,
                "in_agreement": str(m.id) in signed,
            }
            for m in ms
        ],
    }


def mark_delivered(session: Session, job: Job, m: Milestone, me: Member, note: str) -> None:
    if m.status in LOCKED_MS:
        raise HTTPException(400, f"This milestone is {m.status}")
    redelivery = bool(m.delivered_at)
    m.delivered_at = utcnow()
    m.delivery_note = note.strip()[:1500]
    m.client_approved_at = None            # a new delivery needs a fresh review
    m.client_changes_requested_at = None
    m.client_feedback = ""
    session.add(m)
    session.add(AgentAction(
        guild_id=job.guild_id,
        action="milestone.delivered",
        inputs={"job_id": str(job.id), "milestone_id": str(m.id), "by": me.name, "again": redelivery},
        result={"milestone": m.title},
    ))

