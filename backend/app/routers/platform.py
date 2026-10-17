from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlmodel import Session, select

from app.db import get_session
from app.deps import get_platform_admin
from app.models import Broadcast, Guild, MaintenanceWindow, utcnow
from app.services.notices import clear_cache
from app.services.platform import all_guilds, guild_row

router = APIRouter(prefix="/platform", tags=["platform"])


# ---------------- Guild health (P1) ----------------

@router.get("/guilds")
def list_guilds(
    admin: dict = Depends(get_platform_admin),
    session: Session = Depends(get_session),
):
    rows = all_guilds(session)
    return {
        "guilds": rows,
        "count": len(rows),
        "attention_count": sum(1 for r in rows if r["attention_reasons"]),
        "member_count": sum(r["member_count"] for r in rows),
    }


@router.get("/guilds/{guild_id}")
def get_guild(
    guild_id: UUID,
    admin: dict = Depends(get_platform_admin),
    session: Session = Depends(get_session),
):
    guild = session.get(Guild, guild_id)
    if not guild:
        raise HTTPException(404, "Guild not found")
    return guild_row(session, guild)


# ---------------- Broadcasts and maintenance (P3) ----------------

class Window(BaseModel):
    guild_id: UUID | None = None          # None = every guild
    starts_in_minutes: int = Field(default=0, ge=0, le=60 * 24 * 14)
    duration_minutes: int | None = Field(default=None, ge=1, le=60 * 24 * 7)


class BroadcastIn(Window):
    level: str = Field(default="info", pattern="^(info|warning|critical)$")
    title: str = Field(min_length=3, max_length=120)
    body: str = Field(min_length=5, max_length=600)


class MaintenanceIn(Window):
    mode: str = Field(default="read_only", pattern="^(read_only|full_pause)$")
    message: str = Field(min_length=5, max_length=300)
    duration_minutes: int = Field(ge=1, le=60 * 24)   # maintenance must always end on its own

    @model_validator(mode="after")
    def _clean(self):
        self.message = self.message.strip()
        return self


def _times(w: Window) -> tuple[datetime, datetime | None]:
    start = utcnow() + timedelta(minutes=w.starts_in_minutes)
    end = start + timedelta(minutes=w.duration_minutes) if w.duration_minutes else None
    return start, end


def _check_guild(session: Session, guild_id: UUID | None) -> None:
    if guild_id and not session.get(Guild, guild_id):
        raise HTTPException(404, "Guild not found")


def _out(row) -> dict:
    d = row.model_dump()
    now = utcnow()
    d["state"] = (
        "ended" if row.ends_at and row.ends_at <= now
        else "scheduled" if row.starts_at > now
        else "live"
    )
    return d


@router.post("/broadcasts")
def create_broadcast(
    body: BroadcastIn,
    admin: dict = Depends(get_platform_admin),
    session: Session = Depends(get_session),
):
    _check_guild(session, body.guild_id)
    start, end = _times(body)
    b = Broadcast(
        guild_id=body.guild_id, level=body.level, title=body.title.strip(), body=body.body.strip(),
        starts_at=start, ends_at=end, created_by_email=admin["email"],
    )
    session.add(b)
    session.commit()
    session.refresh(b)
    return _out(b)


@router.get("/broadcasts")
def list_broadcasts(
    admin: dict = Depends(get_platform_admin),
    session: Session = Depends(get_session),
):
    rows = session.exec(select(Broadcast).order_by(Broadcast.created_at.desc()).limit(30)).all()
    return [_out(r) for r in rows]


@router.post("/broadcasts/{broadcast_id}/end")
def end_broadcast(
    broadcast_id: UUID,
    admin: dict = Depends(get_platform_admin),
    session: Session = Depends(get_session),
):
    b = session.get(Broadcast, broadcast_id)
    if not b:
        raise HTTPException(404, "Broadcast not found")
    b.ends_at = utcnow()
    session.add(b)
    session.commit()
    session.refresh(b)
    return _out(b)


@router.post("/maintenance")
def create_maintenance(
    body: MaintenanceIn,
    admin: dict = Depends(get_platform_admin),
    session: Session = Depends(get_session),
):
    _check_guild(session, body.guild_id)
    start, end = _times(body)
    w = MaintenanceWindow(
        guild_id=body.guild_id, mode=body.mode, message=body.message,
        starts_at=start, ends_at=end, created_by_email=admin["email"],
    )
    session.add(w)
    session.commit()
    session.refresh(w)
    clear_cache()
    return _out(w)


@router.get("/maintenance")
def list_maintenance(
    admin: dict = Depends(get_platform_admin),
    session: Session = Depends(get_session),
):
    rows = session.exec(select(MaintenanceWindow).order_by(MaintenanceWindow.created_at.desc()).limit(30)).all()
    return [_out(r) for r in rows]


@router.post("/maintenance/{window_id}/end")
def end_maintenance(
    window_id: UUID,
    admin: dict = Depends(get_platform_admin),
    session: Session = Depends(get_session),
):
    w = session.get(MaintenanceWindow, window_id)
    if not w:
        raise HTTPException(404, "Window not found")
    now = utcnow()
    if w.starts_at > now:
        w.starts_at = now   # cancel a scheduled one
    w.ends_at = now
    session.add(w)
    session.commit()
    session.refresh(w)
    clear_cache()
    return _out(w)
