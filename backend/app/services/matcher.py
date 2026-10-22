from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.models import AgentAction, Job, Member
from app.services.ai import AIError, run_ai_json
from app.prompts import JOB_MATCH as SYSTEM
from app.services.capacity import member_capacity, roster_note

class MatchPick(BaseModel):
    top: str
    backup: str | None = None
    reason: str = Field(max_length=500)

def match_job(session: Session, job: Job, feature: str = "match") -> dict:
    candidates = session.exec(
        select(Member)
        .where(Member.guild_id == job.guild_id)
        .where(Member.id != job.referrer_id)
        .where(Member.read_only == False)  # noqa: E712  (14A judge accounts never get work)
    ).all()
    if not candidates:
        raise ValueError("No other members in the guild to match")

    labels = {f"M{i + 1}": m for i, m in enumerate(candidates)}
    # 14B: real capacity, not just a yes/no switch
    roster = "\n".join(
        f"{label}: {m.name} | skills: {', '.join(m.skills) or 'none listed'} | "
        f"rate: ${m.hourly_rate_cents // 100}/hr | availability: {roster_note(member_capacity(session, m))}"
        for label, m in labels.items()
    )

    pick = run_ai_json(
        [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Job:\n{job.description}\n\nMembers:\n{roster}"},
        ],
        feature="match",
        schema=MatchPick,
    )

    top = labels.get(pick.top.strip().upper())
    if not top:
        raise AIError(f"AI picked an unknown label: {pick.top}")
    backup = labels.get((pick.backup or "").strip().upper())
    if backup and backup.id == top.id:
        backup = None

    reason = pick.reason
    for label, m in labels.items():
        reason = reason.replace(label, m.name)

    result = {
        "top_member_id": str(top.id),
        "top_name": top.name,
        "backup_member_id": str(backup.id) if backup else None,
        "backup_name": backup.name if backup else None,
        "reason": reason,
    }
    session.add(AgentAction(
        guild_id=job.guild_id,
        action="job.match",
        inputs={"job_id": str(job.id), "candidates": len(candidates)},
        result=result,
    ))
    return result
