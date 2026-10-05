# The Guild\backend\scripts\test_paypal_payout.py
from dotenv import load_dotenv
load_dotenv()

import os
import uuid
import httpx

from app.services.paypal import _base, auth_headers


def send_payout(receiver_email: str, amount_usd: str = "10.00"):
    batch_id = f"GUILD-PAYOUT-{uuid.uuid4().hex[:12]}"
    payload = {
        "sender_batch_header": {
            "sender_batch_id": batch_id,
            "email_subject": "You have a Guild payout",
            "email_message": "Test payout from The Guild sandbox",
        },
        "items": [
            {
                "recipient_type": "EMAIL",
                "amount": {"value": amount_usd, "currency": "USD"},
                "receiver": receiver_email,
                "note": "Guild Phase 0 payout test",
                "sender_item_id": f"item-{uuid.uuid4().hex[:8]}",
            }
        ],
    }
    r = httpx.post(
        f"{_base()}/v1/payments/payouts",
        headers=auth_headers(),
        json=payload,
        timeout=30,
    )
    return r.status_code, r.json()


if __name__ == "__main__":
    receiver = os.environ["TEST_MEMBER_EMAIL"]
    status, body = send_payout(receiver)
    print(f"HTTP {status}")
    print(body)
    if status in (200, 201):
        print("OK — PayPal Payouts works")
    else:
        print("FAILED — check sandbox balance and Payouts eligibility")