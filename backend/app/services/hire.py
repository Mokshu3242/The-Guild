"""13A Hire the guild by agent.

A client's AI agent gets a quote from a brief, then hires by quote id.
- The AI drafts the milestones. Code checks the budget against the brief, caps the size,
  and stores the quote. The agent can't change a price, because hiring only takes the quote id.
- Hiring the same quote twice returns the same job (safe to retry).
- The job then goes through the normal flow: worker matched, client signs in the portal,
  delivery, approval, PayPal invoice. Nothing about money is automatic here.
"""
import logging
import re
import statistics
from datetime import timedelta
from uuid import UUID

from sqlmodel import Session, select

from app.db import engine
from app.models import AgentAction, Agreement, ApiKey, Guild, Invoice, Job, Member, Milestone, Quote, utcnow
from app.prompts import SCOPE_DRAFT
from app.services.ai import AIError, run_ai_json
from app.services.matcher import match_job
from app.services.portal import ensure_token, portal_url
from app.services.scope_builder import ScopeDraft

logger = logging.getLogger(__name__)

QUOTE_DAYS = 7
MAX_MILESTONES = 4
MIN_MILESTONE_CENTS = 2_000        # $20
MAX_TOTAL_CENTS = 2_500_000        # $25,000. Bigger work needs a person.
QUOTES_PER_DAY = 50                # per key


def money(c: int) -> str:
    return f"${c // 100:,}.{c % 100:02d}"


# ---------------------------------------------------------------- budget check

_AMOUNT = re.compile(
    r"\$\s*(\d[\d,]*(?:\.\d{1,2})?)\s*(k)?\b"
    r"|\b(\d[\d,]*(?:\.\d{1,2})?)\s*(k)?\s*(?:usd|dollars|bucks)\b",
    re.IGNORECASE,
)


def amounts_in(text: str) -> set[int]:
    """Every dollar amount written in the brief, in cents. '$800', '800 USD', '$1.5k'."""
    found = set()
    for m in _AMOUNT.finditer(text):
        num, k = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        try:
            value = float(num.replace(",", ""))
        except ValueError:
            continue
        found.add(round(value * (1000 if k else 1) * 100))
    return found


def guild_rate(session: Session, guild_id) -> int:
    rates = [m.hourly_rate_cents for m in session.exec(select(Member).where(Member.guild_id == guild_id)).all()
             if m.hourly_rate_cents > 0]
    return int(statistics.median(rates)) if rates else 8_000


# ---------------------------------------------------------------- quote

class QuoteError(ValueError):
    pass


def make_quote(session: Session, key: ApiKey, brief: str) -> Quote:
    guild = session.get(Guild, key.guild_id)
    since = utcnow() - timedelta(days=1)
    today = len(session.exec(select(Quote.id).where(Quote.api_key_id == key.id, Quote.created_at >= since)).all())
    if today >= QUOTES_PER_DAY:
        raise QuoteError(f"This key has made {QUOTES_PER_DAY} quotes in the last day. Try again tomorrow.")

    rate = guild_rate(session, guild.id)
    prompt = (
        f"Guild: {guild.name}\n"
        f"Job on file: none yet, this is a new client asking for a quote\n"
        f"Worker's hourly rate: ${rate // 100}/hr (the guild's usual rate)\n\n"
        f"Client brief:\n{brief.strip()}"
    )
    draft = run_ai_json(
        [{"role": "system", "content": SCOPE_DRAFT}, {"role": "user", "content": prompt}],
        schema=ScopeDraft, temperature=0.2, max_tokens=900, feature="hire",
    )

    ms = [{"title": m.title.strip(), "scope": m.scope.strip(), "amount_cents": m.amount_cents}
          for m in draft.milestones[:MAX_MILESTONES]]
    basis = draft.pricing_basis.strip()

    # Code checks the AI: a budget only counts if the client actually wrote it.
    budget = draft.budget_cents if draft.budget_cents and draft.budget_cents in amounts_in(brief) else None
    if draft.budget_cents and budget is None:
        logger.warning("Quote budget %s not found in the brief, priced by effort instead", draft.budget_cents)
        basis = f"About {money(rate)}/hr times the hours this usually takes."
    if budget:
        diff = budget - sum(m["amount_cents"] for m in ms)
        ms[-1]["amount_cents"] += diff      # make it add up exactly
        basis = basis or f"Split the client's {money(budget)} budget by effort."

    for m in ms:
        m["amount_cents"] = round(m["amount_cents"] / 100) * 100   # whole dollars
    if budget:
        ms[-1]["amount_cents"] += budget - sum(m["amount_cents"] for m in ms)
    total = sum(m["amount_cents"] for m in ms)

    if any(m["amount_cents"] < MIN_MILESTONE_CENTS for m in ms):
        raise QuoteError(f"A milestone came out under {money(MIN_MILESTONE_CENTS)}. Add more detail or a bigger budget.")
    if total > MAX_TOTAL_CENTS:
        raise QuoteError(f"This is over {money(MAX_TOTAL_CENTS)}, so a person from the guild needs to quote it.")

    q = Quote(guild_id=guild.id, api_key_id=key.id, brief=brief.strip()[:3000], summary=draft.summary.strip(),
              pricing_basis=basis[:200], budget_cents=budget, milestones=ms, total_cents=total,
              expires_at=utcnow() + timedelta(days=QUOTE_DAYS))
    session.add(q)
    session.flush()
    session.add(AgentAction(
        guild_id=guild.id,
        action="hire.quoted",
        inputs={"key": key.name, "quote_id": str(q.id), "brief_len": len(brief)},
        result={"summary": q.summary, "milestones": len(ms), "total_cents": total, "budget_cents": budget},
    ))
    return q


def quote_out(q: Quote) -> dict:
    return {
        "quote_id": str(q.id),
        "summary": q.summary,
        "pricing_basis": q.pricing_basis,
        "budget_cents": q.budget_cents,
        "total_cents": q.total_cents,
        "total": money(q.total_cents),
        "milestones": [{**m, "amount": money(m["amount_cents"])} for m in q.milestones],
        "expires_at": q.expires_at.isoformat(),
        "status": q.status,
        "how_to_hire": "Call hire with this quote_id and the client's name and email. Prices can't be changed.",
    }


# ---------------------------------------------------------------- hire

def hire(session: Session, key: ApiKey, quote_id, client_name: str, client_email: str) -> tuple[Job, bool]:
    """Returns (job, created). Hiring the same quote again returns the same job."""
    q = session.exec(select(Quote).where(Quote.id == quote_id).with_for_update()).first()
    if not q or q.guild_id != key.guild_id:
        raise LookupError("Quote not found")
    if q.status == "hired" and q.job_id:
        return session.get(Job, q.job_id), False
    expires = q.expires_at if q.expires_at.tzinfo else q.expires_at.replace(tzinfo=utcnow().tzinfo)
    if expires < utcnow():
        raise ValueError("This quote has expired. Ask for a new one.")

    referrer = session.get(Member, key.member_id)
    if not referrer or referrer.guild_id != key.guild_id:
        raise ValueError("The admin who made this key has left the guild. Ask the guild for a new key.")

    job = Job(
        guild_id=q.guild_id, referrer_id=referrer.id, client_name=client_name.strip()[:120],
        client_email=client_email.strip().lower()[:200],
        description=f"{q.summary}\n\nBrief from the client's agent:\n{q.brief}"[:4000],
        source="api", api_key_id=key.id,
    )
    ensure_token(job)
    session.add(job)
    session.flush()
    for m in q.milestones:
        session.add(Milestone(job_id=job.id, title=m["title"][:120], scope=m["scope"][:600], amount=m["amount_cents"]))
    q.status, q.job_id = "hired", job.id
    session.add(q)
    session.add(AgentAction(
        guild_id=q.guild_id,
        action="hire.received",
        inputs={"key": key.name, "job_id": str(job.id), "quote_id": str(q.id)},
        result={"client": job.client_name, "milestones": len(q.milestones), "total_cents": q.total_cents,
                "referrer": referrer.name},
    ))
    return job, True


def match_in_background(job_id) -> None:
    """After a hire: pick a worker with the usual matcher. A person can change it on the job page."""
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if not job or job.worker_id:
            return
        try:
            pick = match_job(session, job)
        except (AIError, ValueError) as e:
            logger.info("No automatic match for job %s: %s", job_id, e)
            session.rollback()
            return
        top = session.get(Member, UUID(pick["top_member_id"]))
        if not top or not top.available:
            session.commit()   # keep the job.match log, leave the choice to a person
            return
        job.worker_id, job.match_reason, job.status = top.id, pick["reason"], "matched"
        session.add(job)
        session.add(AgentAction(
            guild_id=job.guild_id,
            action="hire.matched",
            inputs={"job_id": str(job.id)},
            result={"client": job.client_name, "worker": top.name, "reason": pick["reason"]},
        ))
        session.commit()


# ---------------------------------------------------------------- status for the agent

def job_out(session: Session, job: Job, created: bool | None = None) -> dict:
    ms = session.exec(select(Milestone).where(Milestone.job_id == job.id).order_by(Milestone.created_at, Milestone.id)).all()
    worker = session.get(Member, job.worker_id) if job.worker_id else None
    signed = {mid for a in session.exec(select(Agreement).where(Agreement.job_id == job.id,
                                                                Agreement.kind.in_(["work", "amendment"]))).all()
              for mid in (a.milestone_ids or [])}
    rows = []
    for m in ms:
        inv = session.exec(select(Invoice).where(Invoice.milestone_id == m.id).order_by(Invoice.sent_at.desc())).first()
        rows.append({
            "title": m.title,
            "amount": money(m.amount),
            "amount_cents": m.amount,
            "status": m.status,
            "in_signed_agreement": str(m.id) in signed,
            "delivered": m.delivered_at is not None,
            "approved": m.client_approved_at is not None,
            "invoice": {"status": inv.status, "pay_url": inv.pay_url} if inv else None,
        })
    link = portal_url(job)
    if not signed:
        nxt = "Send the client the portal_url. They read and accept the work agreement there."
    elif any(r["invoice"] and r["invoice"]["status"] == "sent" for r in rows):
        nxt = "An invoice is waiting. The client can pay it from the portal_url or the pay_url."
    else:
        nxt = "The guild is working on it. The client reviews each delivery in the portal_url."
    out = {
        "job_id": str(job.id),
        "status": job.status,
        "client": job.client_name,
        "worker": worker.name if worker else None,
        "portal_url": link or None,
        "total": money(sum(m.amount for m in ms)),
        "agreement_signed": bool(signed),
        "milestones": rows,
        "next_step": nxt,
    }
    if created is not None:
        out["already_hired"] = not created
    return out
