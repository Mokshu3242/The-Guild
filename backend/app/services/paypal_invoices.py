import httpx

from app.services.paypal import _base, auth_headers, usd


def create_invoice(
    invoice_number: str,
    client_email: str,
    amount_cents: int,
    item_name: str,
    note: str = "",
) -> str:
    """Create a draft invoice in PayPal. Returns the PayPal invoice id."""
    payload = {
        "detail": {
            "invoice_number": invoice_number,
            "currency_code": "USD",
            "note": note or "The Guild milestone invoice",
        },
        "primary_recipients": [{"billing_info": {"email_address": client_email}}],
        "items": [
            {
                "name": item_name[:200],
                "quantity": "1",
                "unit_amount": {"currency_code": "USD", "value": usd(amount_cents)},
            }
        ],
    }
    r = httpx.post(
        f"{_base()}/v2/invoicing/invoices",
        headers={**auth_headers(), "PayPal-Request-Id": invoice_number},
        json=payload,
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    if "id" in data:
        return data["id"]
    return data["href"].rstrip("/").split("/")[-1]


def send_invoice(paypal_invoice_id: str) -> None:
    r = httpx.post(
        f"{_base()}/v2/invoicing/invoices/{paypal_invoice_id}/send",
        headers=auth_headers(),
        json={"send_to_invoicer": True},
        timeout=30,
    )
    r.raise_for_status()


def get_invoice(paypal_invoice_id: str) -> dict:
    r = httpx.get(
        f"{_base()}/v2/invoicing/invoices/{paypal_invoice_id}",
        headers=auth_headers(),
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def payer_url(invoice: dict) -> str:
    """The link the client opens to pay."""
    return invoice.get("detail", {}).get("metadata", {}).get("recipient_view_url", "")

def remind_invoice(paypal_invoice_id: str, tier: int, subject: str, note: str) -> None:
    """Ask PayPal to email the client a reminder. One request ID per tier."""
    r = httpx.post(
        f"{_base()}/v2/invoicing/invoices/{paypal_invoice_id}/remind",
        headers={**auth_headers(), "PayPal-Request-Id": f"REMIND-{paypal_invoice_id}-T{tier}"},
        json={"subject": subject[:255], "note": note[:1000], "send_to_invoicer": True},
        timeout=30,
    )
    r.raise_for_status()