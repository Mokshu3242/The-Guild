"""14B Capacity: who is busy, until when. Rules only, no AI.

Milestones have no due dates, so a booking is an estimate from the real work left:
  hours = unfinished milestone amount / the worker's hourly rate ($80 if unset)
  days  = hours / 6, counted in business days
Each member's open jobs are queued one after another, oldest first, starting today.
A member can also say "busy until <date>" (available_from). "Not taking work" is available = False.
"""
import math
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app.models import Job, Member, Milestone, utcnow

HOURS_PER_DAY = 6
DEFAULT_RATE_CENTS = 8_000
ACTIVE = ("matched", "in_progress", "disputed")


def _today() -> datetime:
    now = utcnow()
    now = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def add_business_days(start: datetime, days: int) -> datetime:
    """The day the work ends, counting `days` working days from `start` (start counts if it's a weekday)."""
    d = start
    while d.weekday() >= 5:
        d += timedelta(days=1)
    left = max(1, days) - 1
    while left > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            left -= 1
    return d


def _work_days(session: Session, job: Job, member: Member) -> tuple[int, int]:
    """(business days of work left, cents of work left) for one job."""
    left = [m for m in session.exec(select(Milestone).where(Milestone.job_id == job.id)).all()
            if m.delivered_at is None and m.status not in ("paid", "covered")]
    cents = sum(m.amount for m in left)
    if cents == 0:
        return 0, 0
    hours = cents / (member.hourly_rate_cents or DEFAULT_RATE_CENTS)
    return max(1, math.ceil(hours / HOURS_PER_DAY)), cents


def member_capacity(session: Session, member: Member) -> dict:
    today = _today()
    jobs = session.exec(
        select(Job).where(Job.worker_id == member.id, Job.status.in_(ACTIVE)).order_by(Job.created_at)
    ).all()
    bookings, cursor = [], today
    for j in jobs:
        days, cents = _work_days(session, j, member)
        if not days:
            continue   # delivered, waiting on the client: not taking the member's time
        while cursor.weekday() >= 5:   # work starts on a weekday
            cursor += timedelta(days=1)
        end = add_business_days(cursor, days)
        bookings.append({"job_id": str(j.id), "client": j.client_name, "start": cursor.date().isoformat(),
                         "end": end.date().isoformat(), "days": days, "work_cents": cents})
        cursor = end + timedelta(days=1)

    away_until = _aware(member.available_from)
    if away_until and away_until < today:
        away_until = None
    free_from = max([d for d in (cursor if bookings else today, away_until) if d])
    if not member.available and not away_until:
        state = "off"                       # not taking work, no date given
    elif free_from <= today:
        state = "free"
    else:
        state = "busy"
    return {
        "id": str(member.id),
        "name": member.name,
        "skills": member.skills,
        "state": state,
        "free_from": None if state == "off" else free_from.date().isoformat(),
        "away_until": away_until.date().isoformat() if away_until else None,
        "bookings": bookings,
    }


def member_history(session: Session, member: Member, since: datetime) -> list[dict]:
    """Past work for the board: each job this member delivered something on, from when the job came in
    to the last delivery. Read-only history; matching and hiring never look at it."""
    jobs = session.exec(select(Job).where(Job.worker_id == member.id, Job.status != "open")).all()
    out = []
    for j in jobs:
        ms = session.exec(select(Milestone).where(Milestone.job_id == j.id)).all()
        done = [m for m in ms if m.delivered_at is not None]
        if not done:
            continue
        end = max(_aware(m.delivered_at) for m in done).replace(hour=0, minute=0, second=0, microsecond=0)
        start = min(_aware(j.created_at).replace(hour=0, minute=0, second=0, microsecond=0), end)
        if end < since:
            continue
        outcome = ("covered" if any(m.status == "covered" for m in ms)
                   else "paid" if j.status == "paid" else "delivered")
        out.append({"job_id": str(j.id), "client": j.client_name, "start": start.date().isoformat(),
                    "end": end.date().isoformat(), "work_cents": sum(m.amount for m in done), "outcome": outcome})
    return sorted(out, key=lambda h: h["start"])


def guild_capacity(session: Session, guild_id, weeks: int = 2, past_weeks: int = 0) -> dict:
    today = _today()
    start = today - timedelta(days=today.weekday() + 7 * past_weeks)   # this Monday, or that many weeks back
    members = session.exec(
        select(Member).where(Member.guild_id == guild_id, Member.read_only == False).order_by(Member.name)  # noqa: E712
    ).all()
    rows = []
    for m in members:
        row = member_capacity(session, m)
        row["history"] = member_history(session, m, start) if past_weeks else []
        rows.append(row)
    return {
        "today": today.date().isoformat(),
        "start": start.date().isoformat(),
        "days": (weeks + past_weeks) * 7,
        "hours_per_day": HOURS_PER_DAY,
        "members": rows,
    }


def roster_note(cap: dict) -> str:
    """One phrase for the matcher prompt."""
    if cap["state"] == "off":
        return "not taking new work"
    if cap["state"] == "free":
        return "free now"
    n = len(cap["bookings"])
    jobs = f", {n} job{'s' if n != 1 else ''} in progress" if n else ""
    return f"busy until {datetime.fromisoformat(cap['free_from']).strftime('%b %d')}{jobs}"
