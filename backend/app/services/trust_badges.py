"""Trust badges and reputation summary.

Rules decide the badges from real records. The AI only writes a short summary,
and only when someone clicks the button.
"""
from datetime import timedelta

from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.models import AgentAction, Member, Payout, Subscription, utcnow
from app.services.ai import AIError, run_ai_json

MIN_WORK_PAYOUTS = 3      # "Completed N paid jobs"
MIN_REFERRALS = 2         # "Brought N paying clients"
TOP_EARNER_DAYS = 30
TOP_EARNER_MIN_JOBS = 2   # one lucky job isn't "top earner"

REFERRAL_KINDS = {"referral"}
NOT_WORK_KINDS = REFERRAL_KINDS | {"pool", "claim", "claim_payout", "refund"}


def _ok(p: Payout) -> bool:
    # Count a payout unless it clearly failed. Works whether or not Payout has a status.
    status = (getattr(p, "status", "") or "").lower()
    return status not in {"failed", "returned", "denied", "blocked", "refunded"}


def _joined(m: Member):
    return getattr(m, "joined_at", None) or getattr(m, "created_at", None)


def facts_for(session: Session, member: Member) -> dict:
    guild_members = session.exec(select(Member).where(Member.guild_id == member.guild_id)).all()
    ids = [m.id for m in guild_members]

    mine = [p for p in session.exec(select(Payout).where(Payout.member_id == member.id)).all() if _ok(p)]
    work = [p for p in mine if p.kind not in NOT_WORK_KINDS]
    referrals = [p for p in mine if p.kind in REFERRAL_KINDS]

    sub = session.exec(
        select(Subscription).where(Subscription.member_id == member.id, Subscription.status == "active")
    ).first()

    dated = [m for m in guild_members if _joined(m)]
    founder = min(dated, key=_joined) if dated else None

    # Top earner: most work pay in the last 30 days, with at least 2 jobs, no ties.
    since = utcnow() - timedelta(days=TOP_EARNER_DAYS)
    recent = [
        p for p in session.exec(select(Payout).where(Payout.member_id.in_(ids))).all()
        if _ok(p) and p.kind not in NOT_WORK_KINDS and p.created_at and p.created_at >= since
    ]
    totals: dict = {}
    counts: dict = {}
    for p in recent:
        totals[p.member_id] = totals.get(p.member_id, 0) + p.amount
        counts[p.member_id] = counts.get(p.member_id, 0) + 1
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    top = (
        ranked[0][0]
        if ranked
        and counts.get(ranked[0][0], 0) >= TOP_EARNER_MIN_JOBS
        and (len(ranked) == 1 or ranked[0][1] > ranked[1][1])
        else None
    )

    return {
        "paid_jobs": len(work),
        "referrals": len(referrals),
        "funds_pool": sub is not None,
        "founder": founder is not None and founder.id == member.id,
        "top_earner": top == member.id,
    }


def badges_for(session: Session, member: Member) -> list[dict]:
    f = facts_for(session, member)
    badges = []
    if f["founder"]:
        badges.append({"key": "founder", "label": "Founding member", "tone": "ink"})
    if f["paid_jobs"] >= MIN_WORK_PAYOUTS:
        badges.append({"key": "reliable", "label": f"Completed {f['paid_jobs']} paid jobs", "tone": "guild"})
    if f["referrals"] >= MIN_REFERRALS:
        badges.append({"key": "referrer", "label": f"Brought {f['referrals']} paying clients", "tone": "guild"})
    if f["top_earner"]:
        badges.append({"key": "top_earner", "label": "Top earner this month", "tone": "guild"})
    if f["funds_pool"]:
        badges.append({"key": "pool", "label": "Funds the safety pool", "tone": "seal"})
    return badges


class RepSummary(BaseModel):
    summary: str = Field(min_length=10, max_length=400)


SYSTEM = (
    "You write a short reputation summary of one freelancer for the other members of their guild. "
    "Third person, present tense, warm and plain. Use only the facts given. Never invent numbers, "
    "clients, or skills. If there are no badges, say they are new and have no track record yet. "
    "Two sentences at most. No greeting, no signature. "
    'Return ONLY JSON: {"summary": "..."}'
)


def _fallback(name: str, badges: list[dict]) -> str:
    if not badges:
        return f"{name} is new to the guild and has no track record yet."
    labels = [b["label"][0].lower() + b["label"][1:] for b in badges]
    if len(labels) == 1:
        return f"{name}: {labels[0]}."
    return f"{name}: {', '.join(labels[:-1])}, and {labels[-1]}."


def summarize(session: Session, member: Member, by: Member) -> dict:
    f = facts_for(session, member)
    badges = badges_for(session, member)
    prompt = (
        f"Name: {member.name}\n"
        f"Skills: {', '.join(member.skills or []) or 'none listed'}\n"
        f"Paid jobs completed: {f['paid_jobs']}\n"
        f"Clients they brought who paid: {f['referrals']}\n"
        f"Pays the monthly safety pool fee: {'yes' if f['funds_pool'] else 'no'}\n"
        "Badges:\n" + ("\n".join(f"- {b['label']}" for b in badges) or "- none yet")
    )
    try:
        summary = run_ai_json(
            [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
            schema=RepSummary,
            temperature=0.3,
            max_tokens=220,
        ).summary.strip()
        written_by = "ai"
    except AIError:
        summary = _fallback(member.name, badges)
        written_by = "template"

    session.add(AgentAction(
        guild_id=member.guild_id,
        action="member.reputation_summary",
        inputs={"member": member.name, "by": by.name, "badge_count": len(badges)},
        result={"summary": summary, "written_by": written_by},
    ))
    return {"member_id": str(member.id), "badges": badges, "summary": summary, "written_by": written_by}