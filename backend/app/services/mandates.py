"""13B Agent mandate. The admin sets limits, and the agent acts inside them without a click.

- Reminders: the daily run sends tiers up to remind_max_tier. Higher tiers wait for a person.
- Claims: paid on their own only if the AI said approve, confident enough, no red flags, small enough.
- Advances: paid on their own only if small enough. Every 12B rule is still checked by advances.approve().
- Every money action is credited to the admin who set the mandate, never to "the system".
  If that admin left or lost admin, money actions stop until another admin saves the mandate.
- At most WEEKLY_LIMIT automatic claims and WEEKLY_LIMIT automatic advances per guild per 7 days.
- Platform switches win: AI off, or the "mandate" switch off, pauses all of it.
"""
import logging
from datetime import timedelta

import httpx
from sqlmodel import Session, select

from app.models import Advance, AgentAction, AgentMandate, Claim, Guild, Invoice, Member, utcnow
from app.services.platform_settings import ai_enabled, ai_feature_disabled

logger = logging.getLogger(__name__)

WEEKLY_LIMIT = 3
TIER_NAME = {0: "none", 1: "friendly", 2: "firm", 3: "final"}
FIELDS = ("active", "remind_max_tier", "auto_claim", "claim_max_cents", "claim_min_confidence",
          "auto_advance", "advance_max_cents")


def money(c: int) -> str:
    return f"${c // 100:,}.{c % 100:02d}"


def get(session: Session, guild_id) -> AgentMandate:
    """The saved mandate, or an unsaved one with the defaults."""
    return session.exec(select(AgentMandate).where(AgentMandate.guild_id == guild_id)).first() \
        or AgentMandate(guild_id=guild_id)


def paused(session: Session) -> str | None:
    if not ai_enabled(session):
        return "AI is turned off for the whole platform."
    if ai_feature_disabled(session, "mandate"):
        return "The platform team paused agent mandates."
    return None


def remind_tier(session: Session, guild_id) -> int:
    """Highest reminder tier the daily run may send on its own. 0 = none."""
    m = get(session, guild_id)
    if paused(session) or not m.active:
        return 0
    return max(0, min(3, m.remind_max_tier))


def setter(session: Session, m: AgentMandate) -> Member | None:
    """The admin who answers for automatic money actions."""
    if not m.set_by_id:
        return None
    who = session.get(Member, m.set_by_id)
    return who if who and who.guild_id == m.guild_id and who.role == "admin" else None


def remind_rule(m: AgentMandate) -> str:
    t = m.remind_max_tier
    return f"send reminders up to tier {t} ({TIER_NAME[t]}) on their own" if t else "no reminders on their own"


def claim_rule(m: AgentMandate) -> str:
    return f"pay claims up to {money(m.claim_max_cents)} when the AI says approve with {m.claim_min_confidence}% confidence or more"


def advance_rule(m: AgentMandate) -> str:
    return f"pay advances up to {money(m.advance_max_cents)} that pass every rule"


def _used_this_week(session: Session, guild_id, kind: str) -> int:
    since = utcnow() - timedelta(days=7)
    rows = session.exec(select(AgentAction).where(
        AgentAction.guild_id == guild_id, AgentAction.action == "mandate.applied", AgentAction.created_at >= since,
    )).all()
    return sum(1 for a in rows if (a.inputs or {}).get("kind") == kind)


def _log(session: Session, m: AgentMandate, who: Member, kind: str, rule: str, ref: dict, result: dict) -> None:
    session.add(AgentAction(
        guild_id=m.guild_id,
        action="mandate.applied",
        inputs={"kind": kind, "mandate_id": str(m.id), "set_by": who.name, "rule": rule, **ref},
        result=result,
    ))


# ---------------------------------------------------------------- claims

def claim_check(session: Session, claim: Claim) -> tuple[Member | None, str | None]:
    """(admin who answers for it, None) if the mandate covers this claim, else (None, why not)."""
    m = get(session, claim.guild_id)
    if why := paused(session):
        return None, why
    if not m.active or not m.auto_claim:
        return None, "Claims aren't in the mandate."
    who = setter(session, m)
    if not who:
        return None, "The admin who set the mandate isn't an admin here any more."
    if claim.member_id == who.id:
        return None, "The claim is from the admin who set the mandate, so another admin decides."
    if claim.status != "ai_reviewed":
        return None, f"The claim is {claim.status}."
    if claim.ai_verdict != "approve":
        return None, f"The AI said {claim.ai_verdict.replace('_', ' ') or 'nothing'}."
    if round((claim.ai_confidence or 0) * 100) < m.claim_min_confidence:
        return None, f"The AI was {round((claim.ai_confidence or 0) * 100)}% sure, under {m.claim_min_confidence}%."
    if "Red flags:" in (claim.ai_reason or ""):
        return None, "The AI raised red flags."
    guild = session.get(Guild, claim.guild_id)
    cap = session.get(Invoice, claim.invoice_id).amount * guild.claim_cap_pct // 100
    if cap > m.claim_max_cents:
        return None, f"It would pay {money(cap)}, over the {money(m.claim_max_cents)} limit."
    if (guild.pool_balance - cap) * 4 < guild.pool_balance:
        return None, "It would leave less than a quarter of the pool."
    if _used_this_week(session, claim.guild_id, "claim") >= WEEKLY_LIMIT:
        return None, f"The mandate already paid {WEEKLY_LIMIT} claims this week."
    return who, None


def try_claim(session: Session, claim: Claim) -> dict:
    """Pay the claim if the mandate covers it. Commits on success, rolls back on a PayPal error."""
    from app.services.claims import pay_claim

    who, why = claim_check(session, claim)
    if not who:
        return {"status": "needs_admin", "reason": why}
    m = get(session, claim.guild_id)
    rule = claim_rule(m)
    try:
        result = pay_claim(session, claim.id, who, note=f"Paid under the guild mandate set by {who.name}: {rule}.")
    except (ValueError, httpx.HTTPError) as e:
        session.rollback()
        logger.warning("Mandate couldn't pay claim %s: %s", claim.id, e)
        return {"status": "needs_admin", "reason": f"Couldn't pay it on its own: {str(e)[:150]}"}
    _log(session, m, who, "claim", rule, {"claim_id": str(claim.id), "invoice_id": str(claim.invoice_id)},
         {"amount_cents": result.get("amount_cents", 0), "confidence": round(claim.ai_confidence * 100)})
    session.commit()
    return {"status": "paid", "amount_cents": result.get("amount_cents", 0), "rule": rule, "set_by": who.name}


# ---------------------------------------------------------------- advances

def advance_check(session: Session, adv: Advance) -> tuple[Member | None, str | None]:
    m = get(session, adv.guild_id)
    if why := paused(session):
        return None, why
    if not m.active or not m.auto_advance:
        return None, "Advances aren't in the mandate."
    who = setter(session, m)
    if not who:
        return None, "The admin who set the mandate isn't an admin here any more."
    if adv.member_id == who.id:
        return None, "The request is from the admin who set the mandate, so another admin decides."
    if adv.status != "pending":
        return None, f"The advance is {adv.status}."
    if adv.advance_cents > m.advance_max_cents:
        return None, f"{money(adv.advance_cents)} is over the {money(m.advance_max_cents)} limit."
    if _used_this_week(session, adv.guild_id, "advance") >= WEEKLY_LIMIT:
        return None, f"The mandate already paid {WEEKLY_LIMIT} advances this week."
    return who, None


def try_advance(session: Session, adv: Advance) -> dict:
    """Pay the advance if the mandate covers it. All 12B rules run again inside approve()."""
    from app.services import advances

    who, why = advance_check(session, adv)
    if not who:
        return {"status": "needs_admin", "reason": why}
    m = get(session, adv.guild_id)
    rule = advance_rule(m)
    try:
        result = advances.approve(session, adv, who)
    except (ValueError, PermissionError, httpx.HTTPError) as e:
        session.rollback()
        logger.warning("Mandate couldn't pay advance %s: %s", adv.id, e)
        return {"status": "needs_admin", "reason": str(e)[:200]}
    adv.decided_by = f"{who.name} (mandate)"
    session.add(adv)
    _log(session, m, who, "advance", rule, {"advance_id": str(adv.id), "invoice_id": str(adv.invoice_id)},
         {"amount_cents": result["advance_cents"]})
    session.commit()
    return {"status": "paid", "amount_cents": result["advance_cents"], "rule": rule, "set_by": who.name}


# ---------------------------------------------------------------- settings

def out(session: Session, m: AgentMandate) -> dict:
    who = setter(session, m)
    week = {k: _used_this_week(session, m.guild_id, k) for k in ("claim", "advance")}
    return {
        **{f: getattr(m, f) for f in FIELDS},
        "saved": m.set_by_name != "",
        "set_by": m.set_by_name,
        "set_by_ok": who is not None,
        "updated_at": m.updated_at.isoformat() if m.set_by_name else None,
        "paused": paused(session),
        "weekly_limit": WEEKLY_LIMIT,
        "used_this_week": week,
        "rules": {"remind": remind_rule(m), "claim": claim_rule(m), "advance": advance_rule(m)},
    }


def save(session: Session, admin: Member, changes: dict) -> AgentMandate:
    m = get(session, admin.guild_id)
    before = {f: getattr(m, f) for f in FIELDS}
    for f, v in changes.items():
        if f in FIELDS and v is not None:
            setattr(m, f, v)
    diff = {f: [before[f], getattr(m, f)] for f in FIELDS if before[f] != getattr(m, f)}
    # Whoever saves it answers for it from now on.
    m.set_by_id, m.set_by_name, m.updated_at = admin.id, admin.name, utcnow()
    session.add(m)
    session.add(AgentAction(
        guild_id=admin.guild_id,
        action="mandate.updated",
        inputs={"by": admin.name},
        result={"changes": diff, "rules": [remind_rule(m)]
                + ([claim_rule(m)] if m.auto_claim else []) + ([advance_rule(m)] if m.auto_advance else []),
                "active": m.active},
    ))
    return m
