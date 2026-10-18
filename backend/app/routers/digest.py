import logging
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlmodel import Session, select

from app.config import settings
from app.db import get_session
from app.deps import get_current_member, require_admin
from app.models import Guild, GuildDigest, Member
from app.services.digest import digest_out, latest_digest, publish_digest
from app.services.notices import is_suspended

logger = logging.getLogger(__name__)
router = APIRouter(tags=["digest"])


@router.get("/digests/latest")
def get_latest(
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    d = latest_digest(session, me.guild_id)
    return {"digest": digest_out(d) if d else None}


@router.get("/digests")
def list_digests(
    limit: int = 12,
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    rows = session.exec(
        select(GuildDigest).where(GuildDigest.guild_id == me.guild_id)
        .order_by(GuildDigest.created_at.desc()).limit(max(1, min(limit, 52)))
    ).all()
    return [digest_out(d) for d in rows]


@router.post("/digests/run")
def run_now(
    admin: Member = Depends(require_admin),
    session: Session = Depends(get_session),
):
    """Admin button: write this week's digest now."""
    guild = session.get(Guild, admin.guild_id)
    if not guild:
        raise HTTPException(404, "Guild not found")
    d = publish_digest(session, guild)
    session.commit()
    session.refresh(d)
    return {"digest": digest_out(d)}


@router.post("/tasks/weekly-digest")
def weekly_digest_task(
    x_task_secret: str = Header(default=""),
    session: Session = Depends(get_session),
):
    """Monday cron. One digest per active guild."""
    expected = getattr(settings, "task_secret", "") or ""
    if not expected:
        raise HTTPException(503, "TASK_SECRET is not configured")
    if not secrets.compare_digest(x_task_secret, expected):
        raise HTTPException(401, "Bad task secret")

    results = []
    for guild in session.exec(select(Guild)).all():
        if is_suspended(session, guild.id):
            results.append({"guild": guild.name, "ok": True, "skipped": "suspended"})
            continue
        try:
            d = publish_digest(session, guild)
            session.commit()
            results.append({"guild": guild.name, "ok": True, "written_by": d.written_by})
        except Exception as e:
            session.rollback()
            logger.exception("Digest failed for guild %s", guild.id)
            results.append({"guild": guild.name, "ok": False, "error": type(e).__name__})
    return {"count": len(results), "results": results}
