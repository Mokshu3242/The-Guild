import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.db import engine
from app.models import Invoice, Payout, Subscription, WebhookEvent
from app.routers.pool import apply_subscription_status
from app.services.paypal import cents_from_str
from app.services.pool import credit_pool
from app.services import paypal_webhooks
from app.services.money import process_paid_invoice

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/paypal")
async def paypal_webhook(request: Request):
    raw = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}
    return await run_in_threadpool(_handle_event, headers, raw)


def _handle_event(headers: dict, raw: bytes) -> dict:
    try:
        event = json.loads(raw)
    except ValueError:
        raise HTTPException(400, "Body is not JSON")

    event_id = event.get("id")
    event_type = event.get("event_type", "unknown")
    logger.info("Webhook received: %s (%s)", event_type, event_id)
    if not event_id:
        raise HTTPException(400, "Missing event id")

    if not paypal_webhooks.verify_signature(headers, raw):
        raise HTTPException(400, "Invalid webhook signature")

    with Session(engine) as session:
        seen = session.exec(
            select(WebhookEvent).where(WebhookEvent.paypal_event_id == event_id)
        ).first()
        if seen:
            return {"status": "duplicate"}

        try:
            if event_type == "INVOICING.INVOICE.PAID":
                _on_invoice_paid(session, event)
            elif event_type in ("PAYMENT.PAYOUTSBATCH.SUCCESS", "PAYMENT.PAYOUTSBATCH.DENIED"):
                _on_payout_batch(session, event, event_type)
            elif event_type.startswith("BILLING.SUBSCRIPTION."):
                _on_subscription_status(session, event)
            elif event_type == "PAYMENT.SALE.COMPLETED":
                _on_sale_completed(session, event)
            else:
                logger.info("Ignoring event type %s", event_type)
            session.add(WebhookEvent(paypal_event_id=event_id, type=event_type, processed=True))
            session.commit()
        except IntegrityError:
            session.rollback()
            return {"status": "duplicate"}
        except Exception:
            session.rollback()
            logger.exception("Webhook %s (%s) failed", event_id, event_type)
            raise HTTPException(500, "Handler error")

    return {"status": "ok"}


def _on_invoice_paid(session: Session, event: dict) -> None:
    resource = event.get("resource", {})
    paypal_invoice_id = (resource.get("invoice") or resource).get("id")
    invoice = session.exec(
        select(Invoice).where(Invoice.paypal_invoice_id == paypal_invoice_id)
    ).first()
    if not invoice:
        logger.warning("Paid event for unknown invoice %s", paypal_invoice_id)
        return
    process_paid_invoice(session, invoice.id, source="webhook")


def _on_payout_batch(session: Session, event: dict, event_type: str) -> None:
    batch_id = event.get("resource", {}).get("batch_header", {}).get("payout_batch_id")
    new_status = "completed" if event_type.endswith("SUCCESS") else "failed"
    for payout in session.exec(select(Payout).where(Payout.paypal_batch_id == batch_id)).all():
        payout.status = new_status
        session.add(payout)

def _find_subscription(session: Session, paypal_sub_id: str | None) -> Subscription | None:
    if not paypal_sub_id:
        return None
    return session.exec(
        select(Subscription).where(Subscription.paypal_subscription_id == paypal_sub_id)
    ).first()


def _on_subscription_status(session: Session, event: dict) -> None:
    resource = event.get("resource", {})
    sub = _find_subscription(session, resource.get("id"))
    if not sub:
        logger.warning("Status event for unknown subscription %s", resource.get("id"))
        return
    apply_subscription_status(sub, resource.get("status", ""))
    session.add(sub)


def _on_sale_completed(session: Session, event: dict) -> None:
    resource = event.get("resource", {})
    sub = _find_subscription(session, resource.get("billing_agreement_id"))
    if not sub:
        logger.info("Sale %s is not a pool subscription, ignoring", resource.get("id"))
        return
    total = resource.get("amount", {}).get("total")
    if not total:
        return
    credit_pool(session, sub.guild_id, cents_from_str(total), "subscription", f"sale:{resource['id']}")