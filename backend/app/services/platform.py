"""Platform admin: health across every guild. Counts and levels only, never money."""
from datetime import timedelta

from sqlmodel import Session, func, select

from app.models import AgentAction, Claim, Guild, Job, Member, utcnow
from app.services.pool_forecast import compute as pool_numbers

STALE_DAYS = 14          # no activity this long = needs a look
CLAIM_WAIT_DAYS = 3      # a claim waiting this long = needs a look


def _count(session: Session, stmt) -> int:
    return session.exec(stmt).one()


def guild_row(session: Session, guild: Guild) -> dict:
    """Exactly these fields go to the platform admin. No dollars, no names, no claim text."""
    try:
        health = pool_numbers(session, guild)["verdict"]   # healthy / watch / underfunded
    except Exception:
        health = "unknown"

    waiting = session.exec(
        select(Claim).where(Claim.guild_id == guild.id, Claim.status.in_(["submitted", "ai_reviewed"]))
    ).all()
    now = utcnow()
    oldest_wait_days = max(((now - c.created_at).days for c in waiting), default=0)

    last = session.exec(
        select(AgentAction.created_at)
        .where(AgentAction.guild_id == guild.id)
        .order_by(AgentAction.created_at.desc())
    ).first()
    idle_days = (now - last).days if last else None

    status = getattr(guild, "status", "active") or "active"
    reasons = []
    if status == "suspended":
        reasons.append("Suspended")
    if health == "underfunded":
        reasons.append("Pool underfunded")
    if oldest_wait_days >= CLAIM_WAIT_DAYS:
        reasons.append(f"A claim has waited {oldest_wait_days} days")
    if idle_days is not None and idle_days >= STALE_DAYS:
        reasons.append(f"No activity for {idle_days} days")

    return {
        "id": str(guild.id),
        "name": guild.name,
        "status": status,
        "pool_health": health,
        "member_count": _count(session, select(func.count()).select_from(Member).where(Member.guild_id == guild.id)),
        "admin_count": _count(
            session,
            select(func.count()).select_from(Member).where(Member.guild_id == guild.id, Member.role == "admin"),
        ),
        "active_jobs": _count(
            session,
            select(func.count()).select_from(Job).where(
                Job.guild_id == guild.id, Job.status.in_(["open", "matched", "in_progress"])
            ),
        ),
        "finished_jobs": _count(
            session,
            select(func.count()).select_from(Job).where(Job.guild_id == guild.id, Job.status.in_(["paid", "covered"])),
        ),
        "waiting_claims": len(waiting),
        "last_activity_at": last.isoformat() if last else None,
        "created_at": guild.created_at.isoformat() if getattr(guild, "created_at", None) else None,
        "attention_reasons": reasons,
    }


def all_guilds(session: Session) -> list[dict]:
    guilds = session.exec(select(Guild)).all()
    rows = [guild_row(session, g) for g in guilds]
    # Guilds that need a look first, then by name.
    rows.sort(key=lambda r: (not r["attention_reasons"], r["name"].lower()))
    return rows
