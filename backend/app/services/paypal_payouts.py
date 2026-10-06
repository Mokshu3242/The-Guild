import httpx

from app.services.paypal import _base, auth_headers, usd


def send_batch_payout(items: list[dict], batch_ref: str) -> str:
    """Send one Payouts batch. Returns PayPal's payout_batch_id.

    items: [{receiver_email, amount_cents, note, item_id}]
    batch_ref: a stable id (the invoice id). PayPal rejects a reused
    sender_batch_id, which is our last line of defense against paying twice.
    """
    payload = {
        "sender_batch_header": {
            "sender_batch_id": f"GUILD-{batch_ref}",
            "email_subject": "You have a Guild payout",
            "email_message": "Your share from a Guild job has been paid.",
        },
        "items": [
            {
                "recipient_type": "EMAIL",
                "amount": {"value": usd(it["amount_cents"]), "currency": "USD"},
                "receiver": it["receiver_email"],
                "note": it.get("note", "Guild payout")[:4000],
                "sender_item_id": it["item_id"],
            }
            for it in items
        ],
    }
    r = httpx.post(
        f"{_base()}/v1/payments/payouts",
        headers={**auth_headers(), "PayPal-Request-Id": f"GUILD-{batch_ref}"},
        json=payload,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["batch_header"]["payout_batch_id"]