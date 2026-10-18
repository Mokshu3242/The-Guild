"""Weekly guild digest. Rules count the week, the AI writes the note, it's stored once.

Nothing here runs on page load. It runs from the Monday cron or the admin button.
"""
import logging
from datetime import timedelta

from pydantic import BaseModel, Field
from sqlmodel import Session, func, select

from app.models import AgentAction, Claim, Guild, GuildDigest, Invoice, Job, Member, Milestone, Payout, PoolTx, Reminder, utcnow
from app.prompts import DIGEST as SYSTEM
from app.services.ai import AIError, run_ai_json

logger = logging.getLogger(__name__)

PERIOD_DAYS = 7
OVERDUE_DAYS = 3    # same as the first reminder tier


class DigestDraft(BaseModel):
    narrative: str = Field(min_length=10, max_length=600)


def money(cents: int) -> str:
    return f"${cents // 100:,}.{cents % 100:02d}"


def _sum(session: Session, stmt) -> int:
    return int(session.exec(stmt).one() or 0)


def _stats(session: Session, guild_id, start, end) -> dict:
    def pool(direction: str) -> int:
        return _sum(session, select(func.coalesce(func.sum(PoolTx.amount), 0)).where(
            PoolTx.guild_id == guild_id, PoolTx.direction == direction,
            PoolTx.created_at >= start, PoolTx.created_at < end))

    # Money to members for their work and referrals. Claim payouts are counted separately.
    to_members = _sum(session, select(func.coalesce(func.sum(Payout.amount), 0)).where(
        Payout.guild_id == guild_id, Payout.kind != "claim",
        Payout.created_at >= start, Payout.created_at < end))
    claims_covered = _sum(session, select(func.count()).select_from(Payout).where(
        Payout.guild_id == guild_id, Payout.kind == "claim",
        Payout.created_at >= start, Payout.created_at < end))

    # A paid invoice always writes this log row, so it is the honest "paid this week" count.
    invoices_paid = _sum(session, select(func.count()).select_from(AgentAction).where(
        AgentAction.guild_id == guild_id, AgentAction.action == "invoice.paid.split",
        AgentAction.created_at >= start, AgentAction.created_at < end))

    jobs_posted = _sum(session, select(func.count()).select_from(Job).where(
        Job.guild_id == guild_id, Job.created_at >= start, Job.created_at < end))

    claims_filed = _sum(session, select(func.count()).select_from(Claim).where(
        Claim.guild_id == guild_id, Claim.created_at >= start, Claim.created_at < end))
    claims_waiting = _sum(session, select(func.count()).select_from(Claim).where(
        Claim.guild_id == guild_id, Claim.status.in_(["submitted", "ai_reviewed"])))

    reminders_sent = _sum(session, select(func.count()).select_from(Reminder).where(
        Reminder.guild_id == guild_id, Reminder.sent_at.is_not(None),
        Reminder.sent_at >= start, Reminder.sent_at < end))

    joined_col = getattr(Member, "joined_at", None) or getattr(Member, "created_at")
    new_members = _sum(session, select(func.count()).select_from(Member).where(
        Member.guild_id == guild_id, joined_col >= start, joined_col < end))

    overdue = _sum(session, select(func.count()).select_from(Invoice)
                   .join(Milestone, Invoice.milestone_id == Milestone.id)
                   .join(Job, Milestone.job_id == Job.id)
                   .where(Job.guild_id == guild_id, Invoice.status == "sent",
                          Invoice.sent_at < end - timedelta(days=OVERDUE_DAYS)))

    return {
        "invoices_paid": invoices_paid,
        "paid_to_members_cents": to_members,
        "pool_in_cents": pool("in"),
        "pool_out_cents": pool("out"),
        "claims_covered": claims_covered,
        "claims_filed": claims_filed,
        "claims_waiting": claims_waiting,
        "jobs_posted": jobs_posted,
        "reminders_sent": reminders_sent,
        "new_members": new_members,
        "overdue_invoices": overdue,
    }


def _quiet(s: dict) -> bool:
    keys = ("invoices_paid", "paid_to_members_cents", "pool_in_cents", "pool_out_cents", "claims_covered",
            "claims_filed", "claims_waiting", "jobs_posted", "reminders_sent", "new_members", "overdue_invoices")
    return all(s[k] == 0 for k in keys)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def template_narrative(s: dict) -> str:
    if _quiet(s):
        return "A quiet week for the guild, with no new payments or claims."
    good, watch = [], []
    if s["invoices_paid"]:
        good.append(f"{_plural(s['invoices_paid'], 'invoice')} got paid")
    if s["paid_to_members_cents"]:
        good.append(f"{money(s['paid_to_members_cents'])} went out to members")
    if s["pool_in_cents"]:
        good.append(f"the pool took in {money(s['pool_in_cents'])}")
    if s["claims_covered"]:
        good.append(f"the pool covered {_plural(s['claims_covered'], 'claim')}")
    if s["new_members"]:
        good.append(f"{_plural(s['new_members'], 'new member')} joined")
    if s["jobs_posted"]:
        good.append(f"{_plural(s['jobs_posted'], 'new job')} came in")
    if s["claims_waiting"]:
        watch.append(f"{_plural(s['claims_waiting'], 'claim')} waiting on a decision")
    if s["overdue_invoices"]:
        watch.append(f"{_plural(s['overdue_invoices'], 'invoice')} still overdue")
    text = ("This week " + ", ".join(good) + ".") if good else "A slow week for new work."
    if watch:
        text += " Still open: " + " and ".join(watch) + "."
    return text


def _prompt(guild: Guild, s: dict) -> str:
    return (
        f"Guild: {guild.name}\n"
        f"Period: the last {PERIOD_DAYS} days\n\n"
        f"Invoices paid by clients: {s['invoices_paid']}\n"
        f"Paid out to members for work and referrals: {money(s['paid_to_members_cents'])}\n"
        f"Money into the safety pool: {money(s['pool_in_cents'])}\n"
        f"Money out of the safety pool: {money(s['pool_out_cents'])}\n"
        f"Claims covered by the pool: {s['claims_covered']}\n"
        f"Claims filed: {s['claims_filed']}\n"
        f"Claims waiting on an admin: {s['claims_waiting']}\n"
        f"New jobs posted: {s['jobs_posted']}\n"
        f"Reminders sent to clients: {s['reminders_sent']}\n"
        f"New members: {s['new_members']}\n"
        f"Invoices more than {OVERDUE_DAYS} days unpaid: {s['overdue_invoices']}"
    )


def publish_digest(session: Session, guild: Guild) -> GuildDigest:
    """Builds and stores one digest. The caller commits."""
    end = utcnow()
    start = end - timedelta(days=PERIOD_DAYS)
    s = _stats(session, guild.id, start, end)

    narrative, written_by = template_narrative(s), "template"
    if not _quiet(s):   # no AI call for an empty week, nothing to explain
        try:
            draft = run_ai_json(
                [{"role": "system", "content": SYSTEM}, {"role": "user", "content": _prompt(guild, s)}],
                schema=DigestDraft, temperature=0.4, max_tokens=300, feature="digest",
            )
            if "[" not in draft.narrative:
                narrative, written_by = draft.narrative.strip(), "ai"
        except AIError as e:
            logger.info("Digest fell back to template for guild %s: %s", guild.id, e)

    digest = GuildDigest(guild_id=guild.id, period_start=start, period_end=end,
                         narrative=narrative, stats=s, written_by=written_by)
    session.add(digest)
    session.flush()
    session.add(AgentAction(
        guild_id=guild.id,
        action="digest.published",
        inputs={"period_days": PERIOD_DAYS},
        result={"narrative": narrative, "written_by": written_by},
    ))
    return digest


def latest_digest(session: Session, guild_id) -> GuildDigest | None:
    return session.exec(
        select(GuildDigest).where(GuildDigest.guild_id == guild_id).order_by(GuildDigest.created_at.desc())
    ).first()


def digest_out(d: GuildDigest) -> dict:
    return {
        "id": str(d.id),
        "period_start": d.period_start.isoformat(),
        "period_end": d.period_end.isoformat(),
        "narrative": d.narrative,
        "stats": d.stats,
        "written_by": d.written_by,
        "created_at": d.created_at.isoformat(),
    }
