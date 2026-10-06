from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.db import get_session
from app.deps import get_current_member
from app.models import Guild, Member, PoolTx

router = APIRouter(prefix="/pool", tags=["pool"])


@router.get("")
def my_pool(
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    guild = session.get(Guild, me.guild_id)
    return {
        "guild_id": guild.id,
        "pool_balance_cents": guild.pool_balance,
        "monthly_fee_cents": guild.monthly_fee,
    }


@router.get("/transactions")
def list_pool_transactions(
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    return session.exec(
        select(PoolTx).where(PoolTx.guild_id == me.guild_id).order_by(PoolTx.created_at.desc())
    ).all()