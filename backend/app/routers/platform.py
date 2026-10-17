from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlmodel import Session, select

from app.db import get_session
from app.deps import get_platform_admin
from app.models import Broadcast, Guild, MaintenanceWindow, Member, utcnow
from app.services import platform_settings as ps
from app.services.health import run_health_checks
from app.services.notices import clear_cache
from app.services.platform_audit import log as audit, recent as audit_recent
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
    session.flush()
    audit(session, admin["email"], "broadcast.create", str(b.id),
          {"guild_id": str(body.guild_id or "all"), "level": body.level, "title": b.title})
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
    audit(session, admin["email"], "broadcast.end", str(b.id))
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
    session.flush()
    audit(session, admin["email"], "maintenance.create", str(w.id),
          {"guild_id": str(body.guild_id or "all"), "mode": body.mode,
           "starts_in_minutes": body.starts_in_minutes, "duration_minutes": body.duration_minutes})
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
    audit(session, admin["email"], "maintenance.end", str(w.id))
    session.commit()
    session.refresh(w)
    clear_cache()
    return _out(w)


# ---------------- System status (P2) ----------------

@router.post("/health")
def platform_health(
    admin: dict = Depends(get_platform_admin),
    session: Session = Depends(get_session),
):
    """Live check of the database, PayPal and the AI. Runs only when an admin clicks."""
    return run_health_checks(session)


# ---------------- Kill switches (P4) ----------------

class SettingsIn(BaseModel):
    ai_enabled: bool | None = None
    reminders_enabled: bool | None = None
    ai_disabled_features: list[str] | None = None


@router.get("/settings")
def get_settings(
    admin: dict = Depends(get_platform_admin),
    session: Session = Depends(get_session),
):
    return ps.all_settings(session)


@router.post("/settings")
def update_settings(
    body: SettingsIn,
    admin: dict = Depends(get_platform_admin),
    session: Session = Depends(get_session),
):
    before = ps.all_settings(session)
    changes: dict = {}
    if body.ai_enabled is not None:
        ps.set_ai_enabled(session, body.ai_enabled, admin["email"])
        changes["ai_enabled"] = body.ai_enabled
    if body.reminders_enabled is not None:
        ps.set_reminders_enabled(session, body.reminders_enabled, admin["email"])
        changes["reminders_enabled"] = body.reminders_enabled
    if body.ai_disabled_features is not None:
        changes["ai_disabled_features"] = ps.set_disabled_features(session, body.ai_disabled_features, admin["email"])
    if not changes:
        raise HTTPException(400, "Nothing to change")
    audit(session, admin["email"], "setting.update", inputs=changes,
          result={"before": {k: before[k] for k in changes}})
    session.commit()
    ps.clear_cache()
    return ps.all_settings(session)


# ---------------- Suspend a guild (P4) ----------------

class SuspendIn(BaseModel):
    suspend: bool
    reason: str = Field(default="", max_length=300)


@router.post("/guilds/{guild_id}/suspend")
def suspend_guild(
    guild_id: UUID,
    body: SuspendIn,
    admin: dict = Depends(get_platform_admin),
    session: Session = Depends(get_session),
):
    """Blocks members from the app. Money is untouched: webhooks and payouts keep running."""
    guild = session.get(Guild, guild_id)
    if not guild:
        raise HTTPException(404, "Guild not found")
    if body.suspend and not body.reason.strip():
        raise HTTPException(400, "Give a reason for suspending")
    old = guild.status or "active"
    new = "suspended" if body.suspend else "active"
    if old == new:
        return {"status": new}
    guild.status = new
    session.add(guild)
    audit(session, admin["email"], "guild.suspend" if body.suspend else "guild.unsuspend", str(guild.id),
          inputs={"reason": body.reason.strip()}, result={"from": old, "to": new})
    session.commit()
    clear_cache()
    return {"status": new}


# ---------------- Member lookup (P4, read only) ----------------

@router.get("/members")
def find_members(
    email: str,
    admin: dict = Depends(get_platform_admin),
    session: Session = Depends(get_session),
):
    q = email.strip().lower()
    if len(q) < 3:
        raise HTTPException(400, "Type at least 3 characters of the email")
    col = getattr(Member, "email", None) or getattr(Member, "paypal_email", None)
    if col is None:
        raise HTTPException(501, "Members have no email field to search")
    q_safe = q.replace("\\", "").replace("%", "").replace("_", "\\_")
    members = session.exec(select(Member).where(col.ilike(f"%{q_safe}%")).limit(25)).all()

    results = []
    for m in members:
        g = session.get(Guild, m.guild_id)
        joined = getattr(m, "joined_at", None) or getattr(m, "created_at", None)
        results.append({
            "member_id": str(m.id),
            "name": m.name,
            "email": getattr(m, "email", None) or getattr(m, "paypal_email", "") or "",
            "role": m.role,
            "guild_id": str(m.guild_id),
            "guild_name": g.name if g else "",
            "guild_status": (g.status if g else "") or "active",
            "joined_at": joined.isoformat() if joined else None,
        })
    audit(session, admin["email"], "member.lookup", inputs={"query": q}, result={"matches": len(results)})
    session.commit()
    return {"results": results}


# ---------------- Audit log (P4) ----------------

@router.get("/audit")
def get_audit(
    limit: int = 100,
    admin: dict = Depends(get_platform_admin),
    session: Session = Depends(get_session),
):
    return audit_recent(session, max(1, min(limit, 500)))
