"""Silence counts as approval (clause 3 of the work agreement).

After a delivery the client has REVIEW_DAYS business days to approve or ask for changes.
If they do neither, a daily cron approves the milestone and marks it approved_by="silence".
Rules only. No AI.
"""
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app.models import AgentAction, Job, Milestone, utcnow
from app.services.agreements import REVIEW_DAYS, agreement_for_milestone


def review_deadline(delivered_at: datetime, days: int = REVIEW_DAYS) -> datetime:
    """delivered_at plus N business days (Monday to Friday). Same time of day."""
    t = delivered_at if delivered_at.tzinfo else delivered_at.replace(tzinfo=timezone.utc)
    left = days
    while left > 0:
        t += timedelta(days=1)
        if t.weekday() < 5:
            left -= 1
    return t


def _waiting(m: Milestone) -> bool:
    if not m.delivered_at or m.client_approved_at or m.status in ("paid", "covered"):
        return False
    asked = m.client_changes_requested_at
    return not (asked and asked >= m.delivered_at)   # an open change request stops the clock


def run_auto_approve(session: Session) -> list[dict]:
    """Safe to run many times a day: approved milestones drop out. Commits."""
    now = utcnow()
    rows = session.exec(
        select(Milestone).where(Milestone.delivered_at.is_not(None), Milestone.client_approved_at.is_(None))
    ).all()

    done = []
    for m in rows:
        if not _waiting(m) or review_deadline(m.delivered_at) > now:
            continue
        job = session.get(Job, m.job_id)
        if not job:
            continue
        # The 5-day rule is a clause in the work agreement. No accepted agreement, no rule.
        if not agreement_for_milestone(session, job, m):
            continue
        m.client_approved_at = now
        m.approved_by = "silence"
        session.add(m)
        session.add(AgentAction(
            guild_id=job.guild_id,
            action="milestone.auto_approved",
            inputs={"job_id": str(job.id), "milestone_id": str(m.id), "business_days": REVIEW_DAYS},
            result={"milestone": m.title, "client": job.client_name,
                    "delivered_at": m.delivered_at.isoformat()},
        ))
        done.append({"job_id": str(job.id), "milestone": m.title, "client": job.client_name})

    session.commit()
    return done
