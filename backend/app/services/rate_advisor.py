"""Fair rate advisor.

Rules pick the verdict from peer rates. The AI writes one kind sentence.
"""
from statistics import median

from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.prompts import RATE_ADVICE as SYSTEM
from app.models import AgentAction, Member
from app.services.ai import AIError, run_ai_json

BELOW = 0.80     # under 80% of the peer median
ABOVE = 1.20     # over 120% of the peer median
MIN_PEERS = 2    # fewer than this and a "median" would just be one person's rate


class RateAdvice(BaseModel):
    message: str = Field(min_length=15, max_length=300)

def _skills(m: Member) -> set[str]:
    return {s.strip().lower() for s in (m.skills or []) if s and s.strip()}


def _dollars(cents: int) -> str:
    return f"${cents / 100:,.0f}"


def peer_rates(session: Session, me: Member) -> list[int]:
    mine = _skills(me)
    if not mine:
        return []
    others = session.exec(
        select(Member).where(Member.guild_id == me.guild_id, Member.id != me.id)
    ).all()
    return [p.hourly_rate_cents for p in others if p.hourly_rate_cents > 0 and _skills(p) & mine]


def verdict_for(my_cents: int, med: int | None) -> str:
    if med is None or my_cents <= 0:
        return "not_enough_data"
    if my_cents < med * BELOW:
        return "below_market"
    if my_cents > med * ABOVE:
        return "above_market"
    return "well_positioned"


FALLBACK = {
    "below_market": "Members with your skills charge around {med}/hr and you're at {mine}/hr. You may be able to quote higher on your next job.",
    "well_positioned": "You're right in line with members who share your skills (around {med}/hr). Your rate looks fair.",
    "above_market": "You're above the {med}/hr typical for your skills. That works when your past work shows why, so keep your portfolio sharp.",
}


def advise(session: Session, me: Member) -> dict:
    rates = peer_rates(session, me)
    basis = "skills"
    if len(rates) < MIN_PEERS:
        # Small guild: fall back to everyone's rate.
        rates = [
            p.hourly_rate_cents
            for p in session.exec(
                select(Member).where(Member.guild_id == me.guild_id, Member.id != me.id)
            ).all()
            if p.hourly_rate_cents > 0
        ]
        basis = "guild"
    med = int(median(rates)) if len(rates) >= MIN_PEERS else None
    verdict = verdict_for(me.hourly_rate_cents, med)

    if verdict == "not_enough_data":
        # Nothing to compare. No AI call, no log entry.
        return {
            "verdict": verdict,
            "message": "Not enough members share your skills yet to compare rates fairly.",
            "my_rate_cents": me.hourly_rate_cents,
            "median_cents": None,
            "basis": basis,
            "peer_count": len(rates),
        }

    prompt = (
        f"Skills: {', '.join(sorted(_skills(me)))}\n"
        f"Their rate: {_dollars(me.hourly_rate_cents)}/hr\n"
        f"Typical rate in the guild ({'same skills' if basis == 'skills' else 'all members'}): {_dollars(med)}/hr\n"
        f"Verdict, already decided by rules, do not change it: {verdict.replace('_', ' ')}\n"
        "Say what this means for them and one small thing they could try."
    )
    try:
        message = run_ai_json(
            [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
            schema=RateAdvice,
            feature="rate",
            temperature=0.3,
            max_tokens=200,
        ).message
        written_by = "ai"
        message = message.strip()
        message = message[0].upper() + message[1:] + ("" if message.endswith((".", "!")) else ".")
    except AIError:
        message = FALLBACK[verdict].format(med=_dollars(med), mine=_dollars(me.hourly_rate_cents))
        written_by = "template"

    session.add(AgentAction(
        guild_id=me.guild_id,
        action="rate.advised",
        inputs={"member": me.name, "rate_cents": me.hourly_rate_cents, "peer_count": len(rates)},
        result={"verdict": verdict, "median_cents": med, "message": message, "written_by": written_by},
    ))
    return {
        "verdict": verdict,
        "message": message,
        "basis": basis,
        "my_rate_cents": me.hourly_rate_cents,
        "median_cents": med,
        "peer_count": len(rates),
    }