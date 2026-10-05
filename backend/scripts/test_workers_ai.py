# The Guild\backend\scripts\test_workers_ai.py
from dotenv import load_dotenv
load_dotenv()

from pydantic import BaseModel

from app.services.ai import run_ai


class MatchResult(BaseModel):
    top_member: str
    backup_member: str | None
    reason: str


PROMPT = """You are a job matcher for a freelancer guild.
Given a job and members, pick the best match.
Return ONLY valid JSON matching:
{"top_member": "name", "backup_member": "name or null", "reason": "one line"}

Job: Landing page redesign, needs React + Tailwind, budget $1200, due in 2 weeks.
Members:
- Alice: React, Tailwind, available, $90/hr
- Bob: Django, backend only, available, $80/hr
- Carol: React, unavailable until next month, $70/hr
"""


if __name__ == "__main__":
    text = run_ai([
        {"role": "system", "content": "Return only valid JSON. No markdown."},
        {"role": "user", "content": PROMPT},
    ])
    print("Raw response:")
    print(text)
    cleaned = (
        text.strip()
        .removeprefix("```json")
        .removeprefix("```")
        .removesuffix("```")
        .strip()
    )
    result = MatchResult.model_validate_json(cleaned)
    print("Parsed:")
    print(result)
    print("OK — Workers AI returns valid JSON")