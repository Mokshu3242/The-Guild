"""Client risk score.

Rules decide the level and whether to suggest a deposit.
The AI only explains the facts in plain words.
"""
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.models import (
    AgentAction, Claim, Deposit, Invoice, Job, Member, Milestone, Reminder, utcnow,
)
from app.services.ai import run_ai_json

# Invoice statuses that mean "the client has not paid this".
UNPAID = {"sent", "disputed", "covered"}
LATE_DAYS = 14


class RiskWords(BaseModel):
    reason: str = Field(min_length=10, max_length=400)
    signals: list[str] = Field(default_factory=list, max_length=6)


def _norm(email: str) -> str:
    return (email or "").strip().lower()


def client_history(session: Session, job: Job) -> dict:
    """Facts about this client's work with the guild, this job included.

    A brand-new job has no invoices yet, so it adds nothing. A job that is
    already running (like a ghosted one) should count against the client.
    """
    email = _norm(job.client_email)
    jobs = [
        j for j in session.exec(
            select(Job).where(Job.guild_id == job.guild_id)
        ).all()
        if _norm(j.client_email) == email
    ]
    facts = {
        "past_jobs": len(jobs), "invoices_sent": 0, "invoices_paid": 0,
        "invoices_unpaid": 0, "paid_cents": 0, "unpaid_cents": 0,
        "longest_unpaid_days": 0, "reminders_sent": 0,
        "claims_filed": 0, "claims_paid": 0, "deposits_captured": 0,
    }
    if not jobs:
        return facts

    ms_ids = [m.id for m in session.exec(
        select(Milestone).where(Milestone.job_id.in_([j.id for j in jobs]))
    ).all()]
    if not ms_ids:
        return facts

    invoices = session.exec(select(Invoice).where(Invoice.milestone_id.in_(ms_ids))).all()
    inv_ids = [i.id for i in invoices]
    reminders = session.exec(select(Reminder).where(Reminder.invoice_id.in_(inv_ids))).all() if inv_ids else []
    claims = session.exec(select(Claim).where(Claim.invoice_id.in_(inv_ids))).all() if inv_ids else []
    deposits = session.exec(select(Deposit).where(Deposit.milestone_id.in_(ms_ids))).all()

    now = utcnow()
    for i in invoices:
        if i.status in UNPAID:
            started = getattr(i, "sent_at", None) or i.created_at
            facts["longest_unpaid_days"] = max(facts["longest_unpaid_days"], (now - started).days)

    facts.update(
        invoices_sent=len(invoices),
        invoices_paid=sum(1 for i in invoices if i.status == "paid"),
        invoices_unpaid=sum(1 for i in invoices if i.status in UNPAID),
        paid_cents=sum(i.amount for i in invoices if i.status == "paid"),
        unpaid_cents=sum(i.amount for i in invoices if i.status in UNPAID),
        reminders_sent=len(reminders),
        claims_filed=len(claims),
        claims_paid=sum(1 for c in claims if c.status == "paid"),
        deposits_captured=sum(1 for d in deposits if d.status == "captured"),
    )
    return facts


def _dollars(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def _readable(f: dict) -> str:
    """Facts in plain words, money in dollars, so the AI never says 'cents'."""
    return "\n".join([
        f"- Jobs with this client: {f['past_jobs']}",
        f"- Invoices: {f['invoices_sent']} sent, {f['invoices_paid']} paid, {f['invoices_unpaid']} not paid",
        f"- Paid so far: {_dollars(f['paid_cents'])}",
        f"- Not paid yet: {_dollars(f['unpaid_cents'])}",
        f"- Oldest unpaid invoice: {f['longest_unpaid_days']} days",
        f"- Payment reminders sent: {f['reminders_sent']}",
        f"- Safety pool claims: {f['claims_filed']} filed, {f['claims_paid']} paid out",
        f"- Deposits captured: {f['deposits_captured']}",
    ])


def risk_level(f: dict) -> str:
    """The rule. Same facts always give the same level."""
    if f["invoices_sent"] == 0:
        return "unknown"
    if f["claims_paid"] > 0 or f["longest_unpaid_days"] > LATE_DAYS:
        return "high"
    if f["invoices_unpaid"] > 0 or f["reminders_sent"] > 0 or f["claims_filed"] > 0:
        return "medium"
    return "low"


def suggests_deposit(level: str) -> bool:
    return level in ("medium", "high")


SYSTEM = (
    "You explain a client's payment record to a freelancer. "
    "The risk level is already decided by fixed rules. Do not change it or argue with it. "
    "Use only the facts given. Never invent numbers, names, or events. "
    "reason: one or two short plain sentences saying why the level fits. "
    "signals: up to 4 short bullets in plain English, like 'Paid 3 of 4 invoices'. "
    "Write money in dollars exactly as given. Skip any fact that is zero unless it matters. "
    'Return ONLY JSON: {"reason": "...", "signals": ["..."]}'
)


def assess_client(session: Session, job: Job, me: Member) -> dict:
    facts = client_history(session, job)
    level = risk_level(facts)

    if level == "unknown":
        # No history means nothing to explain. Skip the AI call.
        words = RiskWords(
            reason="This client has no past invoices with the guild, so there is no track record yet.",
            signals=[],
        )
    else:
        lines = _readable(facts)
        words = run_ai_json(
            [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"Risk level: {level}\nFacts:\n{lines}"},
            ],
            schema=RiskWords,
            temperature=0.1,
            max_tokens=400,
        )

    deposit = suggests_deposit(level)
    job.client_risk = level
    job.client_risk_reason = words.reason
    session.add(job)
    session.add(AgentAction(
        guild_id=job.guild_id,
        action="client.risk_scored",
        inputs={"job_id": str(job.id), "by": me.name, "facts": facts},
        result={"level": level, "suggest_deposit": deposit,
                "reason": words.reason, "signals": words.signals},
    ))
    return {"level": level, "reason": words.reason,
            "signals": words.signals, "suggest_deposit": deposit, "facts": facts}