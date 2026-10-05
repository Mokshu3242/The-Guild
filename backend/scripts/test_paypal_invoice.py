# The Guild\backend\scripts\test_paypal_invoice.py
from dotenv import load_dotenv
load_dotenv()

import os
import httpx
import uuid

from app.services.paypal import _base, auth_headers


def create_invoice(client_email: str) -> str:
    payload = {
        "detail": {
            "invoice_number": f"GUILD-TEST-{uuid.uuid4().hex[:8]}",
            "currency_code": "USD",
            "note": "Guild Phase 0 test invoice",
        },
        "primary_recipients": [
            {"billing_info": {"email_address": client_email}}
        ],
        "items": [
            {
                "name": "Design milestone 1",
                "quantity": "1",
                "unit_amount": {"currency_code": "USD", "value": "100.00"},
            }
        ],
    }
    r = httpx.post(
        f"{_base()}/v2/invoicing/invoices",
        headers=auth_headers(),
        json=payload,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["href"].rstrip("/").split("/")[-1]


def send_invoice(invoice_id: str) -> int:
    r = httpx.post(
        f"{_base()}/v2/invoicing/invoices/{invoice_id}/send",
        headers=auth_headers(),
        json={"send_to_invoicer": True},
        timeout=30,
    )
    r.raise_for_status()
    return r.status_code


if __name__ == "__main__":
    client_email = os.environ["TEST_CLIENT_EMAIL"]
    invoice_id = create_invoice(client_email)
    print(f"Created invoice: {invoice_id}")
    status = send_invoice(invoice_id)
    print(f"Sent invoice, status: {status}")
    print("OK — PayPal invoice works")