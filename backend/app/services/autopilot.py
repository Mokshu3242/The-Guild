"""Autopilot: rules find what needs attention, AI explains, a person approves.

Nothing here moves money. Approving a card calls endpoints that already exist.
"""
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.models import AgentAction, Deposit, Invoice, Job, Member, Milestone, Reminder, utcnow
from app.services.ai import AIError, run_ai_json
from app.prompts import AUTOPILOT as SYSTEM
from app.services.client_risk import client_history, risk_level

try:  # reuse the reminder schedule if reminders.py exposes it
    from app.services.reminders import TIER_DAYS  # type: ignore
except ImportError:
    TIER_DAYS = {1: 3, 2: 7, 3: 14}

OPEN_STALL_DAYS = 3   # open job, no worker
SCOPE_STALL_DAYS = 3  # matched job, no milestones
MAX_FINDINGS = 12     # keep the list readable and the AI call small

# Lower number shows first.
PRIORITY = {"remind": 0, "deposit": 1, "match": 2, "scope_hint": 3}


def _days_since(dt) -> int:
    return (utcnow() - dt).days if dt else 0


def _overdue_invoices(session: Session, guild_id) -> list[dict]:
    out = []
    rows = session.exec(
        select(Invoice, Milestone, Job)
        .join(Milestone, Invoice.milestone_id == Milestone.id)
        .join(Job, Milestone.job_id == Job.id)
        .where(Job.guild_id == guild_id, Invoice.status == "sent")
    ).all()
    for inv, ms, job in rows:
        days = _days_since(getattr(inv, "sent_at", None) or inv.created_at)
        due = max((t for t, d in TIER_DAYS.items() if days >= d), default=None)
        if due is None:
            continue
        sent = {r.tier for r in session.exec(select(Reminder).where(Reminder.invoice_id == inv.id)).all()}
        if sent and max(sent) >= due:
            continue  # this stage was already handled
        out.append({
            "id": f"remind-{inv.id}",
            "kind": "remind",
            "job_id": str(job.id),
            "title": f"{job.client_name}: {ms.title}",
            "rule_reason": f"The invoice for {ms.title} has been unpaid for {days} days, and reminder {due} of 3 hasn't gone out.",
            "action_endpoint": f"/invoices/{inv.id}/remind",
            "action_body": {},
        })
    return out


def _deposits_for_risky_clients(session: Session, guild_id) -> list[dict]:
    out = []
    jobs = session.exec(
        select(Job).where(
            Job.guild_id == guild_id,
            Job.status.in_(["matched", "in_progress"]),
            Job.worker_id.is_not(None),
        )
    ).all()
    for job in jobs:
        # Same rule as 7A, worked out fresh, so it doesn't depend on someone clicking "Score".
        level = risk_level(client_history(session, job))
        if level != "high":
            continue
        for ms in session.exec(
            select(Milestone).where(Milestone.job_id == job.id, Milestone.status == "pending")
        ).all():
            held = session.exec(
                select(Deposit).where(Deposit.milestone_id == ms.id, Deposit.status.in_(["created", "authorized"]))
            ).first()
            invoiced = session.exec(select(Invoice).where(Invoice.milestone_id == ms.id)).first()
            if held or invoiced:
                continue
            out.append({
                "id": f"deposit-{ms.id}",
                "kind": "deposit",
                "job_id": str(job.id),
                "title": f"{job.client_name}: {ms.title}",
                "rule_reason": f"{job.client_name} is a high-risk client, and {ms.title} (${ms.amount / 100:,.2f}) has no deposit hold or invoice yet.",
                "action_endpoint": f"/jobs/{job.id}/milestones/{ms.id}/deposit",
                "action_body": {},
            })
    return out


def _open_jobs_without_worker(session: Session, guild_id) -> list[dict]:
    out = []
    for job in session.exec(
        select(Job).where(Job.guild_id == guild_id, Job.status == "open", Job.worker_id.is_(None))
    ).all():
        days = _days_since(job.created_at)
        if days < OPEN_STALL_DAYS:
            continue
        out.append({
            "id": f"match-{job.id}",
            "kind": "match",
            "job_id": str(job.id),
            "title": job.client_name,
            "rule_reason": f"{job.client_name}'s job was posted {days} days ago and still has no worker.",
            "action_endpoint": f"/jobs/{job.id}/match",
            "action_body": {"auto_assign": False},
        })
    return out


def _matched_without_milestones(session: Session, guild_id) -> list[dict]:
    out = []
    for job in session.exec(
        select(Job).where(Job.guild_id == guild_id, Job.status == "matched", Job.worker_id.is_not(None))
    ).all():
        if session.exec(select(Milestone).where(Milestone.job_id == job.id)).first():
            continue
        days = _days_since(job.created_at)
        if days < SCOPE_STALL_DAYS:
            continue
        out.append({
            "id": f"scope-{job.id}",
            "kind": "scope_hint",
            "job_id": str(job.id),
            "title": job.client_name,
            "rule_reason": f"{job.client_name}'s job has a worker but no milestones after {days} days, so nothing can be invoiced yet.",
            "action_endpoint": "",
            "action_body": {},
        })
    return out


class FindingReason(BaseModel):
    finding_id: str
    reason: str = Field(min_length=10, max_length=280)


class BatchReasons(BaseModel):
    reasons: list[FindingReason] = Field(default_factory=list, max_length=MAX_FINDINGS)

def _ai_reasons(findings: list[dict]) -> dict[str, str]:
    if not findings:
        return {}
    bullets = "\n".join(f"- finding_id={f['id']}: {f['rule_reason']}" for f in findings)
    try:
        batch = run_ai_json(
            [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"Findings:\n{bullets}\n\nWrite {len(findings)} sentences."},
            ],
            schema=BatchReasons,
            temperature=0.2,
            max_tokens=900,
        )
    except AIError:
        return {}
    ids = {f["id"] for f in findings}
    return {r.finding_id: r.reason for r in batch.reasons if r.finding_id in ids}


def scan(session: Session, me: Member) -> dict:
    gid = me.guild_id
    findings = (
        _overdue_invoices(session, gid)
        + _deposits_for_risky_clients(session, gid)
        + _open_jobs_without_worker(session, gid)
        + _matched_without_milestones(session, gid)
    )
    findings.sort(key=lambda f: PRIORITY[f["kind"]])
    total = len(findings)
    findings = findings[:MAX_FINDINGS]

    ai = _ai_reasons(findings)
    for f in findings:
        f["ai_reason"] = ai.get(f["id"], "")  # empty means: show the rule reason only

    kinds = sorted({f["kind"] for f in findings})
    session.add(AgentAction(
        guild_id=gid,
        action="autopilot.scan",
        inputs={"by": me.name},
        result={"found": total, "shown": len(findings), "kinds": kinds, "ai_wrote": len(ai)},
    ))

    if not total:
        summary = "Everything is caught up. Nothing needs you right now."
    elif total > len(findings):
        summary = f"{total} things need attention. Showing the {len(findings)} most urgent."
    else:
        summary = f"{total} thing{'s' if total != 1 else ''} need{'s' if total == 1 else ''} attention."
    return {"findings": findings, "summary": summary}