import json
import logging

import httpx

from app.config import settings
from app.services.paypal import _base, auth_headers

logger = logging.getLogger(__name__)


def verify_signature(headers: dict, raw_body: bytes) -> bool:
    """Ask PayPal whether this webhook is genuine.

    We splice in the raw body exactly as received, because
    re-encoding the JSON can make PayPal's check fail.
    """
    if not settings.paypal_webhook_id:
        logger.error("PAYPAL_WEBHOOK_ID is not set, rejecting webhook")
        return False

    fields = {
        "transmission_id": headers.get("paypal-transmission-id"),
        "transmission_time": headers.get("paypal-transmission-time"),
        "cert_url": headers.get("paypal-cert-url"),
        "auth_algo": headers.get("paypal-auth-algo"),
        "transmission_sig": headers.get("paypal-transmission-sig"),
        "webhook_id": settings.paypal_webhook_id,
    }
    if not all(fields.values()):
        return False

    body = json.dumps(fields)[:-1] + ', "webhook_event": ' + raw_body.decode("utf-8") + "}"
    r = httpx.post(
        f"{_base()}/v1/notifications/verify-webhook-signature",
        headers=auth_headers(),
        content=body,
        timeout=30,
    )
    if r.status_code != 200:
        logger.warning("Signature check HTTP %s: %s", r.status_code, r.text)
        return False
    status = r.json().get("verification_status")
    if status != "SUCCESS":
        logger.warning(
            "Signature %s using webhook id ending ...%s",
            status, settings.paypal_webhook_id[-4:],
        )
    return status == "SUCCESS"