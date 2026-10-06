import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlmodel import Session, select

from app.config import settings
from app.db import get_session
from app.deps import get_current_member, require_admin
from app.models import Guild, Member, PoolTx, Subscription, utcnow
from app.services import paypal_subscriptions as subs
from app.services.paypal import cents_from_str
from app.services.pool import credit_pool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pool", tags=["pool"])

ACTIVE_STATES = ("pending", "active", "suspended")


def _paypal_error(e: httpx.HTTPStatusError) -> HTTPException:
    logger.error("PayPal error %s: %s", e.response.status_code, e.response.text)
    return HTTPException(502, f"PayPal error: {e.response.text[:300]}")


def _my_subscription(session: Session, me: Member) -> Subscription | None:
    return session.exec(
        select(Subscription)
        .where(Subscription.member_id == me.id)
        .where(Subscription.status.in_(ACTIVE_STATES))
        .order_by(Subscription.created_at.desc())
    ).first()


# ---------- Pool info ----------

@router.get("")
def my_pool(
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    guild = session.get(Guild, me.guild_id)
    active = session.exec(
        select(Subscription)
        .where(Subscription.guild_id == guild.id)
        .where(Subscription.status == "active")
    ).all()
    return {
        "guild_id": guild.id,
        "pool_balance_cents": guild.pool_balance,
        "monthly_fee_cents": guild.monthly_fee,
        "plan_ready": bool(guild.paypal_plan_id),
        "active_subscribers": len(active),
    }


@router.get("/transactions")
def list_pool_transactions(
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    return session.exec(
        select(PoolTx).where(PoolTx.guild_id == me.guild_id).order_by(PoolTx.created_at.desc())
    ).all()


# ---------- Admin: create the plan ----------

@router.post("/plan")
def create_pool_plan(
    admin: Member = Depends(require_admin),
    session: Session = Depends(get_session),
):
    guild = session.get(Guild, admin.guild_id)
    if guild.paypal_plan_id:
        return {"status": "exists", "plan_id": guild.paypal_plan_id}
    try:
        product_id = subs.create_product(f"{guild.name} Safety Pool")
        plan_id = subs.create_plan(product_id, f"{guild.name} monthly pool", guild.monthly_fee)
    except httpx.HTTPStatusError as e:
        raise _paypal_error(e)

    guild.paypal_plan_id = plan_id
    session.add(guild)
    session.commit()
    return {"status": "created", "plan_id": plan_id, "monthly_fee_cents": guild.monthly_fee}


# ---------- Member: subscribe ----------

@router.post("/subscribe")
def subscribe(
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    guild = session.get(Guild, me.guild_id)
    if not guild.paypal_plan_id:
        raise HTTPException(400, "Your guild admin hasn't set up the pool plan yet")

    existing = _my_subscription(session, me)
    if existing and existing.status == "active":
        raise HTTPException(400, "You already have an active pool subscription")
    if existing and existing.status == "pending":
        return existing  # reuse the same approval link

    try:
        created = subs.create_subscription(
            plan_id=guild.paypal_plan_id,
            custom_id=str(me.id),
            return_url=f"{settings.public_base_url}/pool/subscription/return",
            cancel_url=f"{settings.public_base_url}/pool/subscription/return?cancelled=1",
        )
    except httpx.HTTPStatusError as e:
        raise _paypal_error(e)

    sub = Subscription(
        guild_id=guild.id,
        member_id=me.id,
        paypal_subscription_id=created["id"],
        approve_url=created["approve_url"],
        status="pending",
    )
    session.add(sub)
    session.commit()
    session.refresh(sub)
    return sub


@router.get("/subscription")
def my_subscription(
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    sub = _my_subscription(session, me)
    if not sub:
        raise HTTPException(404, "No pool subscription")
    return sub


@router.post("/subscription/sync")
def sync_subscription(
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    """Ask PayPal for real status and payments. Backup for missed webhooks."""
    sub = _my_subscription(session, me)
    if not sub:
        raise HTTPException(404, "No pool subscription")

    try:
        details = subs.get_subscription(sub.paypal_subscription_id)
        txs = subs.list_transactions(sub.paypal_subscription_id)
    except httpx.HTTPStatusError as e:
        raise _paypal_error(e)

    apply_subscription_status(sub, details.get("status", ""))
    session.add(sub)

    credited = 0
    for tx in txs:
        if tx.get("status") != "COMPLETED":
            continue
        gross = tx.get("amount_with_breakdown", {}).get("gross_amount", {}).get("value")
        if not gross:
            continue
        if credit_pool(session, sub.guild_id, cents_from_str(gross), "subscription", f"sale:{tx['id']}"):
            credited += 1

    session.commit()
    return {
        "subscription_status": sub.status,
        "paypal_status": details.get("status"),
        "payments_found": len(txs),
        "newly_credited": credited,
    }


@router.post("/subscription/cancel")
def cancel_my_subscription(
    me: Member = Depends(get_current_member),
    session: Session = Depends(get_session),
):
    sub = _my_subscription(session, me)
    if not sub:
        raise HTTPException(404, "No pool subscription")
    try:
        subs.cancel_subscription(sub.paypal_subscription_id)
    except httpx.HTTPStatusError as e:
        raise _paypal_error(e)
    sub.status = "cancelled"
    session.add(sub)
    session.commit()
    return {"status": "cancelled"}


@router.get("/subscription/return", response_class=HTMLResponse, include_in_schema=False)
def subscription_return(cancelled: int = 0):
    msg = "You cancelled. No money was taken." if cancelled else "You're in! You can close this tab."
    return f"<html><body style='font-family:sans-serif;padding:40px'><h2>The Guild</h2><p>{msg}</p></body></html>"


# ---------- Shared helper ----------

def apply_subscription_status(sub: Subscription, paypal_status: str) -> None:
    mapping = {
        "APPROVAL_PENDING": "pending",
        "APPROVED": "pending",
        "ACTIVE": "active",
        "SUSPENDED": "suspended",
        "CANCELLED": "cancelled",
        "EXPIRED": "cancelled",
    }
    new = mapping.get(paypal_status)
    if not new:
        return
    if new == "active" and sub.status != "active":
        sub.activated_at = utcnow()
    sub.status = new