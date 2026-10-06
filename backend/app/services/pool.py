import logging
from uuid import UUID

from sqlmodel import Session, select

from app.models import AgentAction, Guild, PoolTx

logger = logging.getLogger(__name__)


def credit_pool(
    session: Session,
    guild_id: UUID,
    amount_cents: int,
    source: str,
    external_ref: str,
) -> bool:
    """Add money to the pool once per external_ref. Returns True if added.

    The caller commits.
    """
    if amount_cents <= 0:
        return False

    guild = session.exec(
        select(Guild).where(Guild.id == guild_id).with_for_update()
    ).one()

    exists = session.exec(
        select(PoolTx).where(PoolTx.external_ref == external_ref)
    ).first()
    if exists:
        return False

    guild.pool_balance += amount_cents
    session.add(guild)
    session.add(PoolTx(
        guild_id=guild.id,
        amount=amount_cents,
        direction="in",
        source=source,
        external_ref=external_ref,
    ))
    session.add(AgentAction(
        guild_id=guild.id,
        action="pool.credit",
        inputs={"source": source, "external_ref": external_ref},
        result={"amount_cents": amount_cents, "new_balance": guild.pool_balance},
    ))
    logger.info("Pool +%s cents (%s %s)", amount_cents, source, external_ref)
    return True