"""13A Public API for a client's AI agent. Auth is an API key, not a member login.

POST /api/v1/quote          {brief}                              -> a priced quote with a quote_id
POST /api/v1/hire           {quote_id, client_name, client_email} -> the job and its portal link
GET  /api/v1/jobs/{job_id}                                        -> where the job is now
"""
import time
from collections import defaultdict, deque
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.db import get_session
from app.models import ApiKey, Job, utcnow
from app.services import api_keys, hire
from app.services.ai import AIError
from app.services.notices import active_maintenance

router = APIRouter(prefix="/api/v1", tags=["public api"])

# Per key, per process. Render runs one instance, so this is enough for now.
LIMITS = {"quote": (5, 60), "any": (60, 60)}     # (requests, seconds)
_hits: dict[tuple[str, str], deque] = defaultdict(deque)


def _limit(key: ApiKey, kind: str) -> None:
    n, window = LIMITS[kind]
    q = _hits[(str(key.id), kind)]
    now = time.monotonic()
    while q and q[0] < now - window:
        q.popleft()
    if len(q) >= n:
        raise HTTPException(429, f"Too many requests. This key can make {n} {kind} calls a minute.")
    q.append(now)


def require_key(
    session: Session = Depends(get_session),
    x_api_key: str = Header(default=""),
    authorization: str = Header(default=""),
) -> ApiKey:
    raw = x_api_key or (authorization[7:] if authorization.lower().startswith("bearer ") else "")
    if not raw:
        raise HTTPException(401, "Send your guild API key in the X-API-Key header.")
    key = api_keys.resolve(session, raw)
    if not key:
        raise HTTPException(401, "That API key isn't valid or was turned off.")
    if active_maintenance(session, key.guild_id):
        raise HTTPException(503, "The guild is paused for maintenance right now. Try again later.")
    _limit(key, "any")
    key.request_count += 1
    key.last_used_at = utcnow()
    session.add(key)
    session.commit()
    return key


class QuoteIn(BaseModel):
    brief: str = Field(min_length=30, max_length=3000,
                       description="What the client wants, in plain words. Add a budget like $800 if there is one.")


class HireIn(BaseModel):
    quote_id: UUID
    client_name: str = Field(min_length=2, max_length=120)
    client_email: str = Field(min_length=5, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@router.post("/quote")
def quote(body: QuoteIn, key: ApiKey = Depends(require_key), session: Session = Depends(get_session)):
    _limit(key, "quote")
    try:
        q = hire.make_quote(session, key, body.brief)
    except hire.QuoteError as e:
        session.rollback()
        raise HTTPException(422, str(e))
    except AIError:
        session.rollback()
        raise HTTPException(503, "Quotes are paused right now. Try again in a few minutes.")
    session.commit()
    return hire.quote_out(q)


@router.post("/hire")
def hire_guild(body: HireIn, background: BackgroundTasks, key: ApiKey = Depends(require_key),
               session: Session = Depends(get_session)):
    try:
        job, created = hire.hire(session, key, body.quote_id, body.client_name, body.client_email)
    except LookupError as e:
        session.rollback()
        raise HTTPException(404, str(e))
    except ValueError as e:
        session.rollback()
        raise HTTPException(400, str(e))
    session.commit()
    if created:
        background.add_task(hire.match_in_background, job.id)
    return hire.job_out(session, job, created=created)


@router.get("/jobs/{job_id}")
def job_status(job_id: UUID, key: ApiKey = Depends(require_key), session: Session = Depends(get_session)):
    job = session.get(Job, job_id)
    # An agent only sees jobs that came in through its own key.
    if not job or job.api_key_id != key.id:
        raise HTTPException(404, "Job not found")
    return hire.job_out(session, job)
