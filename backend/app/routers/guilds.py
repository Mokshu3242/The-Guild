import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.auth import get_current_user
from app.db import get_session
from app.deps import get_current_member, require_admin
from app.models import Guild, Member

router = APIRouter(prefix="/guilds", tags=["guilds"])


class CreateGuildIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    your_name: str = Field(min_length=1, max_length=80)


class JoinGuildIn(BaseModel):
    invite_code: str
    name: str = Field(min_length=1, max_length=80)
    paypal_email: str = ""
    skills: list[str] = []
    hourly_rate_cents: int = Field(default=0, ge=0)


def _already_member(session: Session, user_id: UUID) -> bool:
    return session.exec(select(Member).where(Member.user_id == user_id)).first() is not None


@router.post("")
def create_guild(
    body: CreateGuildIn,
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    user_id = UUID(user["sub"])
    if _already_member(session, user_id):
        raise HTTPException(400, "You already belong to a guild")

    guild = Guild(name=body.name, invite_code=secrets.token_urlsafe(8))
    member = Member(
        guild_id=guild.id,
        user_id=user_id,
        name=body.your_name,
        email=user.get("email", ""),
        role="admin",
    )
    session.add(guild)
    session.add(member)
    session.commit()
    session.refresh(guild)
    session.refresh(member)
    return {"guild": guild, "member": member}


@router.post("/join")
def join_guild(
    body: JoinGuildIn,
    user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    user_id = UUID(user["sub"])
    if _already_member(session, user_id):
        raise HTTPException(400, "You already belong to a guild")

    guild = session.exec(
        select(Guild).where(Guild.invite_code == body.invite_code.strip())
    ).first()
    if not guild:
        raise HTTPException(404, "Invalid invite code")

    member = Member(
        guild_id=guild.id,
        user_id=user_id,
        name=body.name,
        email=user.get("email", ""),
        paypal_email=body.paypal_email,
        skills=body.skills,
        hourly_rate_cents=body.hourly_rate_cents,
    )
    session.add(member)
    session.commit()
    session.refresh(member)
    return {"guild_id": guild.id, "member": member}


@router.get("/{guild_id}")
def get_guild(
    guild_id: UUID,
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    if me.guild_id != guild_id:
        raise HTTPException(403, "Not your guild")
    return session.get(Guild, guild_id)


@router.get("/{guild_id}/members")
def list_members(
    guild_id: UUID,
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    if me.guild_id != guild_id:
        raise HTTPException(403, "Not your guild")
    return session.exec(select(Member).where(Member.guild_id == guild_id)).all()


@router.post("/{guild_id}/invite")
def rotate_invite(
    guild_id: UUID,
    admin: Member = Depends(require_admin),
    session: Session = Depends(get_session),
):
    if admin.guild_id != guild_id:
        raise HTTPException(403, "Not your guild")
    guild = session.get(Guild, guild_id)
    guild.invite_code = secrets.token_urlsafe(8)
    session.add(guild)
    session.commit()
    return {"invite_code": guild.invite_code}