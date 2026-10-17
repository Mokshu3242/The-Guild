"""Broadcast banners and maintenance windows.

Maintenance is enforced in get_current_member (deps.py), so it knows which guild
the request is for. Webhooks, cron tasks, and /platform never go through that
dependency, so they keep working during maintenance. No payment is ever lost.
"""
import time

from fastapi import HTTPException
from sqlmodel import Session, or_, select

from app.models import Broadcast, MaintenanceWindow, utcnow

READ_METHODS = {"GET", "HEAD", "OPTIONS"}
ALWAYS_ALLOWED = ("/me/notices",)   # the banner and the maintenance page must still load
UPCOMING_HOURS = 24                 # show "maintenance starts in..." this far ahead
CACHE_SECONDS = 5

_cache: dict = {"at": 0.0, "rows": []}


def _live(model, now):
    return (model.starts_at <= now) & (model.ends_at.is_(None) | (model.ends_at > now))


def _for_guild(model, guild_id):
    return or_(model.guild_id.is_(None), model.guild_id == guild_id)


def active_broadcasts(session: Session, guild_id) -> list[Broadcast]:
    now = utcnow()
    return session.exec(
        select(Broadcast).where(_live(Broadcast, now), _for_guild(Broadcast, guild_id)).order_by(Broadcast.starts_at)
    ).all()


def _all_live_windows(session: Session) -> list[MaintenanceWindow]:
    """Every live window, cached for a few seconds so normal requests stay fast."""
    if time.monotonic() - _cache["at"] < CACHE_SECONDS:
        return _cache["rows"]
    now = utcnow()
    rows = session.exec(select(MaintenanceWindow).where(_live(MaintenanceWindow, now))).all()
    for r in rows:
        session.expunge(r)
    _cache.update(at=time.monotonic(), rows=rows)
    return rows


def clear_cache() -> None:
    _cache["at"] = 0.0


def active_maintenance(session: Session, guild_id) -> MaintenanceWindow | None:
    rows = [w for w in _all_live_windows(session) if w.guild_id is None or w.guild_id == guild_id]
    if not rows:
        return None
    return next((w for w in rows if w.mode == "full_pause"), rows[0])  # full pause wins


def upcoming_maintenance(session: Session, guild_id) -> MaintenanceWindow | None:
    now = utcnow()
    from datetime import timedelta

    return session.exec(
        select(MaintenanceWindow)
        .where(
            MaintenanceWindow.starts_at > now,
            MaintenanceWindow.starts_at <= now + timedelta(hours=UPCOMING_HOURS),
            _for_guild(MaintenanceWindow, guild_id),
        )
        .order_by(MaintenanceWindow.starts_at)
    ).first()


def enforce(session: Session, guild_id, method: str, path: str) -> None:
    """Called for every member request. Raises 503 when maintenance blocks it."""
    if path.startswith(ALWAYS_ALLOWED):
        return
    w = active_maintenance(session, guild_id)
    if not w:
        return
    if w.mode == "full_pause" or method not in READ_METHODS:
        raise HTTPException(503, w.message)
