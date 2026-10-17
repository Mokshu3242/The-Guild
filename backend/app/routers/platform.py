from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.db import get_session
from app.deps import get_platform_admin
from app.models import Guild
from app.services.platform import all_guilds, guild_row

router = APIRouter(prefix="/platform", tags=["platform"])


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
