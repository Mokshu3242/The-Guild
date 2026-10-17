"""Skill gap: the AI lists the skills a job needs, code checks who in the guild has them."""
import re

from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.models import AgentAction, Job, Member
from app.prompts import SKILL_GAP as SYSTEM
from app.services.ai import run_ai_json


class SkillGapDraft(BaseModel):
    required_skills: list[str] = Field(min_length=1, max_length=8)
    proposed_role: str = Field(min_length=5, max_length=200)


# Different spellings of the same skill. Keys and values are already normalized.
ALIASES = {
    "postgres": "postgresql", "psql": "postgresql",
    "js": "javascript", "ts": "typescript",
    "reactjs": "react", "nextjs": "next", "next": "next",
    "nodejs": "node", "vuejs": "vue",
    "tailwindcss": "tailwind",
    "copy": "copywriting", "copywriter": "copywriting",
    "ux": "uxdesign", "ui": "uidesign",
    "amazonwebservices": "aws",
    "golang": "go",
}


def _key(skill: str) -> str:
    """'Next.js' -> 'next', 'Tailwind CSS' -> 'tailwind', 'Postgres' -> 'postgresql'.

    Exact match after cleanup, never substring, so 'java' never matches 'javascript'.
    """
    s = (skill or "").strip().lower()
    s = re.sub(r"\.js$|js$", "", s) if s not in {"js"} else s
    s = re.sub(r"[^a-z0-9+#]", "", s)
    s = ALIASES.get(s, s)
    if s.endswith("css") and len(s) > 3 and s != "css":
        s = ALIASES.get(s[:-3], s[:-3])
    return s


def assess_gap(session: Session, job: Job, me: Member) -> dict:
    # Who could take the job: everyone except the member who posted it.
    candidates = session.exec(
        select(Member).where(Member.guild_id == job.guild_id, Member.id != job.referrer_id)
    ).all()

    draft = run_ai_json(
        [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Job: {job.description}"},
        ],
        schema=SkillGapDraft,
        temperature=0.1,
        max_tokens=300,
    )

    # Clean up and de-duplicate what the AI returned.
    required: list[str] = []
    seen: set[str] = set()
    for s in draft.required_skills:
        k = _key(s)
        if k and k not in seen:
            seen.add(k)
            required.append(s.strip())
    if not required:
        raise ValueError("The AI didn't find any concrete skills in this job.")

    # Rules decide coverage.
    covered_by, uncovered = [], []
    for skill in required:
        k = _key(skill)
        who = [m for m in candidates if any(_key(x) == k for x in (m.skills or []))]
        if who:
            covered_by.append({
                "skill": skill,
                "members": [m.name for m in who],
                "available": [m.name for m in who if m.available],
            })
        else:
            uncovered.append(skill)

    coverage = "full" if not uncovered else ("none" if len(uncovered) == len(required) else "partial")

    result = {
        "coverage": coverage,
        "required_skills": required,
        "covered_by": covered_by,
        "uncovered_skills": uncovered,
        "proposed_role": draft.proposed_role.strip(),
        "member_count": len(candidates),
    }
    job.skill_coverage = coverage
    job.skill_gap = result
    session.add(job)
    session.add(AgentAction(
        guild_id=job.guild_id,
        action="skill.gap_checked",
        inputs={"job_id": str(job.id), "by": me.name, "client": job.client_name},
        result={
            "coverage": coverage,
            "required_skills": required,
            "uncovered_skills": uncovered,
            "proposed_role": result["proposed_role"],
        },
    ))
    return result