"""Work agreements (client) and the Member Pledge (member).

Rules write the terms from a fixed template, filled in with the job's real data.
The AI only writes a short plain-English summary, and code checks it before it is shown.
Accepting stores the exact text and its SHA-256 hash, so nobody can change it later unnoticed.

Not legal advice: this is a standard template. Guilds should have their own terms reviewed.
"""
import hashlib
import logging

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.db import engine
from app.models import AgentAction, Agreement, Guild, Job, Member, Milestone

logger = logging.getLogger(__name__)

WORK_VERSION = "work-1"
PLEDGE_VERSION = "pledge-1"
REVIEW_DAYS = 5          # business days of silence before a delivery counts as approved (11C)
REPORT_DAYS = 7          # days a member has to report a direct payment


# ---------------------------------------------------------------- helpers

def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def money(cents: int) -> str:
    return f"${cents // 100:,}.{cents % 100:02d}"


def client_ip(request: Request | None) -> str:
    """Render sits behind a proxy, so the real address is the first X-Forwarded-For entry."""
    if not request:
        return ""
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "")[:64]


def _milestones(session: Session, job: Job) -> list[Milestone]:
    return session.exec(
        select(Milestone).where(Milestone.job_id == job.id).order_by(Milestone.created_at, Milestone.id)
    ).all()


def _work_rows(session: Session, job: Job) -> list[Agreement]:
    return session.exec(
        select(Agreement)
        .where(Agreement.job_id == job.id, Agreement.kind.in_(["work", "amendment"]))
        .order_by(Agreement.accepted_at)
    ).all()


def _signed_ids(rows: list[Agreement]) -> set[str]:
    return {mid for r in rows for mid in (r.milestone_ids or [])}


def _unsigned(milestones: list[Milestone], signed: set[str]) -> list[Milestone]:
    """Milestones that still need the client's agreement: not yet billed and not covered by a signature."""
    return [m for m in milestones if m.status == "pending" and str(m.id) not in signed]


# ---------------------------------------------------------------- work agreement text

def render_work(session: Session, job: Job, milestones: list[Milestone]) -> str:
    guild = session.get(Guild, job.guild_id)
    worker = session.get(Member, job.worker_id) if job.worker_id else None
    total = sum(m.amount for m in milestones)
    by = f"{worker.name}, a member of {guild.name}" if worker else f"a member of {guild.name}"

    lines = [
        "WORK AGREEMENT",
        f"Template {WORK_VERSION}",
        "",
        f"Client: {job.client_name} ({job.client_email})",
        f"Guild: {guild.name}, a freelancer collective on The Guild",
        f"Work done by: {by}",
        "",
        "1. The work",
    ]
    for i, m in enumerate(milestones, 1):
        scope = (m.scope or "As described in the project.").strip()
        lines.append(f"   {i}. {m.title} ({money(m.amount)}): {scope}")
    lines += [
        f"   Total: {money(total)}",
        "",
        "2. Paying",
        "   You pay each milestone through the guild's PayPal invoice or deposit hold, so every payment",
        "   is recorded against this agreement. Please don't pay anyone directly.",
        "",
        "3. Delivery and approval",
        "   When a milestone is delivered, you can approve it or ask for changes on your client page.",
        f"   If you don't respond within {REVIEW_DAYS} business days of a delivery, it counts as approved.",
        "",
        "4. Changes and extra work",
        "   Changes that fit the agreed scope are included. New work becomes a new milestone with its",
        "   own price, and you accept it the same way before it starts.",
        "",
        "5. Late payment",
        "   If an invoice stays unpaid, the guild sends reminders after 3, 8 and 14 days. After that,",
        "   the guild may handle the unpaid amount itself, including collecting it for the member.",
        "",
        "6. Ownership",
        "   You own each delivered milestone once it is paid in full. Until then, it stays with the member.",
        "",
        "7. Stopping early",
        "   Either side can stop the project. You pay for milestones delivered or approved up to that point.",
        "",
        "8. Honesty",
        "   Both sides confirm that the information they give is true. If either side acts dishonestly,",
        "   for example by using a false identity, reversing a payment for work that was delivered and",
        "   approved, or paying outside the guild invoice to avoid it, the other side may pause the work,",
        "   share the facts with PayPal, and use any remedy the law allows.",
        "",
        "9. Records",
        "   This agreement, delivery notes, approvals and payment records kept by The Guild are the",
        "   record of this work. They may be shared with PayPal and used in any dispute about it.",
        "",
        "10. Disagreements",
        "   Please raise any problem on your client page first. If that doesn't settle it, both sides",
        "   will try mediation before going to court.",
        "",
        "11. Signing",
        "   By typing your name and accepting, you agree that this is a binding agreement,",
        "   signed electronically.",
    ]
    return "\n".join(lines)


def rules_summary(session: Session, job: Job, milestones: list[Milestone]) -> str:
    """Written by code, so it can never misstate the terms. Shown until the AI summary passes its check."""
    guild = session.get(Guild, job.guild_id)
    worker = session.get(Member, job.worker_id) if job.worker_id else None
    who = f"{worker.name} from {guild.name}" if worker else guild.name
    n = len(milestones)
    total = sum(m.amount for m in milestones)
    each = "it" if n == 1 else "each one"
    return (
        f"You're hiring {who} for {n} milestone{'s' if n != 1 else ''}, {money(total)} in total. "
        f"You pay {each} through PayPal after it's delivered, and you have {REVIEW_DAYS} business days "
        "to approve it or ask for changes."
    )


# ---------------------------------------------------------------- work agreement state

def agreement_for_milestone(session: Session, job: Job, milestone: Milestone) -> Agreement | None:
    """The latest accepted agreement that covers this milestone, if any."""
    mid = str(milestone.id)
    for row in reversed(_work_rows(session, job)):
        if mid in (row.milestone_ids or []):
            return row
    return None


def require_agreement(session: Session, job: Job, milestone: Milestone) -> None:
    if not agreement_for_milestone(session, job, milestone):
        raise HTTPException(
            400,
            "The client hasn't accepted the work agreement for this milestone yet. "
            "Share the client link so they can review and accept it.",
        )


def work_state(session: Session, job: Job) -> dict:
    """Everything the client page and the member panel need about the agreement."""
    milestones = _milestones(session, job)
    rows = _work_rows(session, job)
    signed = _signed_ids(rows)
    pending = _unsigned(milestones, signed)
    text = render_work(session, job, milestones) if milestones else ""
    digest = sha256(text) if text else ""

    ai_ok = bool(job.agreement_summary) and job.agreement_summary_hash == digest
    return {
        "needs_signature": bool(pending),
        "is_amendment": bool(pending) and bool(rows),
        "new_titles": [m.title for m in pending],
        "new_total_cents": sum(m.amount for m in pending),
        "text": text,
        "hash": digest,
        "summary": job.agreement_summary if ai_ok else (rules_summary(session, job, milestones) if milestones else ""),
        "summary_by": "ai" if ai_ok else "rules",
        "signed_ids": sorted(signed),
        "signed": [
            {
                "kind": r.kind,
                "signer": r.signer_name,
                "accepted_at": r.accepted_at.isoformat(),
                "hash": r.sha256,
                "milestones": len(r.milestone_ids or []),
                "total_cents": r.total_cents,
                "body": r.body,
            }
            for r in rows
        ],
    }


def accept_work(session: Session, job: Job, name: str, seen_hash: str, request: Request | None) -> Agreement:
    """The client accepts the agreement as shown. The caller commits."""
    milestones = _milestones(session, job)
    rows = _work_rows(session, job)
    if not _unsigned(milestones, _signed_ids(rows)):
        raise HTTPException(409, "There's nothing new to accept. You're all set.")

    text = render_work(session, job, milestones)
    digest = sha256(text)
    if seen_hash != digest:
        raise HTTPException(409, "The agreement changed while you were reading it. Please review it again.")

    row = Agreement(
        guild_id=job.guild_id,
        job_id=job.id,
        kind="amendment" if rows else "work",
        template_version=WORK_VERSION,
        body=text,
        sha256=digest,
        milestone_ids=[str(m.id) for m in milestones],
        total_cents=sum(m.amount for m in milestones),
        signer_name=name.strip()[:80],
        signer_email=job.client_email,
        ip=client_ip(request),
        user_agent=(request.headers.get("user-agent", "") if request else "")[:300],
    )
    session.add(row)
    session.add(AgentAction(
        guild_id=job.guild_id,
        action="agreement.accepted",
        inputs={"job_id": str(job.id), "by": row.signer_name, "client": job.client_name},
        result={"kind": row.kind, "milestones": len(row.milestone_ids),
                "total_cents": row.total_cents, "hash": digest[:12]},
    ))
    return row


# ---------------------------------------------------------------- AI summary (written once, checked by code)

class SummaryDraft(BaseModel):
    summary: str = Field(min_length=30, max_length=420)


_writing: set = set()


def write_summary_in_background(job_id) -> None:
    """Runs after the client page has loaded, never while the client waits.

    The AI must repeat the real total. If it doesn't, or invents placeholders, code throws it away
    and the rules-written summary stays.
    """
    if job_id in _writing:
        return
    _writing.add(job_id)
    from app.prompts import AGREEMENT_SUMMARY
    from app.services.ai import AIError, run_ai_json

    try:
        with Session(engine) as s:
            job = s.get(Job, job_id)
            if not job:
                return
            milestones = _milestones(s, job)
            if not milestones:
                return
            text = render_work(s, job, milestones)
            digest = sha256(text)
            if job.agreement_summary_hash == digest:
                return
            total = money(sum(m.amount for m in milestones))
            try:
                draft = run_ai_json(
                    [{"role": "system", "content": AGREEMENT_SUMMARY},
                     {"role": "user", "content": f"Total to repeat exactly: {total}\n\nAGREEMENT TEXT:\n{text}"}],
                    schema=SummaryDraft, temperature=0.1, max_tokens=250, feature="agreement",
                )
            except AIError as e:
                logger.info("Agreement summary skipped for job %s: %s", job_id, e)
                return
            summary = draft.summary.strip()
            if total not in summary or "[" in summary:
                logger.info("Agreement summary rejected by the check for job %s", job_id)
                return
            job.agreement_summary, job.agreement_summary_hash = summary, digest
            s.add(job)
            s.commit()
    finally:
        _writing.discard(job_id)


# ---------------------------------------------------------------- Member Pledge

def render_pledge(guild: Guild, member: Member) -> str:
    return "\n".join([
        "MEMBER PLEDGE",
        f"Template {PLEDGE_VERSION}",
        "",
        f"Member: {member.name} ({member.email})",
        f"Guild: {guild.name}",
        "",
        "1. The safety pool",
        f"   Every paid invoice sends {guild.pool_pct}% to the guild's safety pool. Members can also pay",
        f"   {money(guild.monthly_fee)} a month into it. The pool covers members when a client never pays.",
        "",
        "2. Honest claims",
        "   I only ask the pool to cover an invoice when a client really hasn't paid for work I delivered.",
        "   My statement and evidence are true. If a claim turns out to be false, I pay back what the pool",
        "   paid me, and the guild may remove me.",
        "",
        "3. Claim limits",
        f"   The pool covers up to {guild.claim_cap_pct}% of an unpaid invoice, once I've been a member for",
        f"   {guild.claim_wait_days} days and the invoice is {guild.claim_overdue_days} days overdue.",
        "",
        "4. Paid on the side",
        f"   If a client pays me directly for guild work, I tell the guild within {REPORT_DAYS} days and pay",
        "   the guild's shares.",
        "",
        "5. Handing over the debt",
        "   When the pool covers an unpaid invoice, I hand the right to collect it to the guild. If that",
        f"   client later pays me directly, I pass the money to the guild within {REPORT_DAYS} days.",
        "",
        "6. Advances",
        "   If the guild pays me early for an invoice, that money is repaid from the client's payment first.",
        "   If the invoice goes unpaid because of something I did, I repay the advance, and the guild may",
        "   take it from my future payouts.",
        "",
        "7. Fair process",
        "   Before anything happens because of this pledge, I'm told the facts and can respond.",
        "   The AI may point out patterns, but a person always decides.",
        "",
        "8. Signing",
        "   By typing my name and accepting, I agree to this pledge, signed electronically.",
    ])


def _pledge_row(session: Session, member: Member) -> Agreement | None:
    return session.exec(
        select(Agreement)
        .where(Agreement.member_id == member.id, Agreement.kind == "pledge",
               Agreement.template_version == PLEDGE_VERSION)
        .order_by(Agreement.accepted_at.desc())
    ).first()


def pledge_signed(session: Session, member: Member) -> bool:
    return _pledge_row(session, member) is not None


def pledge_state(session: Session, member: Member) -> dict:
    guild = session.get(Guild, member.guild_id)
    row = _pledge_row(session, member)
    text = row.body if row else render_pledge(guild, member)
    return {
        "signed": bool(row),
        "signed_at": row.accepted_at.isoformat() if row else None,
        "signer": row.signer_name if row else "",
        "text": text,
        "hash": row.sha256 if row else sha256(text),
    }


def sign_pledge(session: Session, member: Member, name: str, seen_hash: str, request: Request | None) -> Agreement:
    """The caller commits."""
    if pledge_signed(session, member):
        raise HTTPException(409, "You already signed the Member Pledge")
    guild = session.get(Guild, member.guild_id)
    text = render_pledge(guild, member)
    digest = sha256(text)
    if seen_hash != digest:
        raise HTTPException(409, "The pledge changed while you were reading it. Please review it again.")
    row = Agreement(
        guild_id=guild.id,
        member_id=member.id,
        kind="pledge",
        template_version=PLEDGE_VERSION,
        body=text,
        sha256=digest,
        signer_name=name.strip()[:80],
        signer_email=member.email,
        ip=client_ip(request),
        user_agent=(request.headers.get("user-agent", "") if request else "")[:300],
    )
    session.add(row)
    session.add(AgentAction(
        guild_id=guild.id,
        action="pledge.signed",
        inputs={"by": member.name},
        result={"hash": digest[:12]},
    ))
    return row
