"""Pool health: rules do the math and pick a verdict, the AI writes one sentence."""
from datetime import timedelta

from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.models import AgentAction, Claim, Guild, Invoice, Member, Milestone, Job, Payout, PoolTx, utcnow
from app.prompts import POOL_FORECAST as SYSTEM
from app.services.ai import AIError, run_ai_json

WINDOW_DAYS = 90        # look back this far for income and payouts
MAX_POOL_PCT = 20


class ForecastMessage(BaseModel):
    message: str = Field(min_length=20, max_length=400)


def _dollars(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def _monthly(session: Session, guild_id, direction: str) -> int:
    """Average money in or out of the pool per month, over the window. Uses the pool ledger,
    so it counts invoice slices, member fees and recoveries, not just subscriptions."""
    since = utcnow() - timedelta(days=WINDOW_DAYS)
    rows = session.exec(
        select(PoolTx).where(PoolTx.guild_id == guild_id, PoolTx.direction == direction, PoolTx.created_at >= since)
    ).all()
    if direction == "in":
        rows = [r for r in rows if r.source != "founding"]  # one-off seed money isn't income
    return sum(r.amount for r in rows) * 30 // WINDOW_DAYS


def _typical_claim(session: Session, guild: Guild) -> int:
    """What a claim usually costs: the average real claim payout, or if there are none yet,
    the cap applied to the average invoice."""
    paid = session.exec(select(Payout).where(Payout.guild_id == guild.id, Payout.kind == "claim")).all()
    if paid:
        return sum(p.amount for p in paid) // len(paid)
    invoices = session.exec(
        select(Invoice)
        .join(Milestone, Invoice.milestone_id == Milestone.id)
        .join(Job, Milestone.job_id == Job.id)
        .where(Job.guild_id == guild.id)
    ).all()
    if not invoices:
        return 0
    avg_invoice = sum(i.amount for i in invoices) // len(invoices)
    return avg_invoice * guild.claim_cap_pct // 100


def _open_claims(session: Session, guild_id) -> list[Claim]:
    return session.exec(
        select(Claim).where(Claim.guild_id == guild_id, Claim.status.in_(["submitted", "ai_reviewed"]))
    ).all()


def compute(session: Session, guild: Guild) -> dict:
    balance = guild.pool_balance
    income = _monthly(session, guild.id, "in")
    payouts = _monthly(session, guild.id, "out")
    typical = _typical_claim(session, guild)
    waiting = _open_claims(session, guild.id)

    # Money already promised to claims that are waiting.
    waiting_cents = 0
    for c in waiting:
        inv = session.get(Invoice, c.invoice_id)
        if inv:
            waiting_cents += inv.amount * guild.claim_cap_pct // 100

    free = max(balance - waiting_cents, 0)
    covers = free // typical if typical > 0 else None   # None = no claims to size yet

    if typical > 0 and balance < waiting_cents + typical:
        verdict = "underfunded"
    elif payouts > income:
        verdict = "watch"
    else:
        verdict = "healthy"

    # Suggest a higher cut only when money out is beating money in.
    suggested = guild.pool_pct
    if verdict != "healthy" and payouts > income:
        suggested = min(guild.pool_pct + (1 if payouts <= income * 2 else 2), MAX_POOL_PCT)

    return {
        "verdict": verdict,
        "balance_cents": balance,
        "monthly_income_cents": income,
        "monthly_payouts_cents": payouts,
        "typical_claim_cents": typical,
        "waiting_claims": len(waiting),
        "waiting_cents": waiting_cents,
        "claims_covered": covers,
        "current_pool_pct": guild.pool_pct,
        "suggested_pool_pct": suggested,
    }


def forecast(session: Session, guild: Guild, by: Member) -> dict:
    n = compute(session, guild)
    covers = "unknown (no claims or invoices yet)" if n["claims_covered"] is None else str(n["claims_covered"])
    prompt = (
        f"Verdict, decided by rules: {n['verdict']}\n"
        f"Pool balance: {_dollars(n['balance_cents'])}\n"
        f"Claims waiting for a decision: {n['waiting_claims']} (up to {_dollars(n['waiting_cents'])})\n"
        f"Typical claim: {_dollars(n['typical_claim_cents'])}\n"
        f"More claims the pool can cover after those: {covers}\n"
        f"Money in per month (last 90 days): {_dollars(n['monthly_income_cents'])}\n"
        f"Money out per month (last 90 days): {_dollars(n['monthly_payouts_cents'])}\n"
        f"Pool cut now: {n['current_pool_pct']}%\n"
        + (f"Suggested pool cut: {n['suggested_pool_pct']}%\n" if n["suggested_pool_pct"] != n["current_pool_pct"] else "")
    )
    try:
        message = run_ai_json(
            [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
            feature="forecast",
            schema=ForecastMessage, temperature=0.2, max_tokens=220,
        ).message.strip()
        written_by = "ai"
    except AIError:
        c = n["claims_covered"]
        fallback = {
            "healthy": f"The pool is in good shape{f' and can cover about {c} more claims' if c else ''}.",
            "watch": f"The pool pays out more each month than it takes in. Consider raising the pool cut to {n['suggested_pool_pct']}%.",
            "underfunded": f"The pool can't cover the {n['waiting_claims']} waiting claim(s) plus one more. Consider raising the pool cut to {n['suggested_pool_pct']}%.",
        }
        message = fallback[n["verdict"]]
        written_by = "template"

    result = {**n, "message": message, "written_by": written_by, "created_at": utcnow().isoformat()}
    session.add(AgentAction(guild_id=guild.id, action="pool.forecast", inputs={"by": by.name}, result=result))
    return result


def latest_forecast(session: Session, guild_id) -> dict | None:
    row = session.exec(
        select(AgentAction)
        .where(AgentAction.guild_id == guild_id, AgentAction.action == "pool.forecast")
        .order_by(AgentAction.created_at.desc())
    ).first()
    return row.result if row else None