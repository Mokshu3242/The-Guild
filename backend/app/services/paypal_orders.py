import httpx

from app.services.paypal import _base, auth_headers, usd


def create_authorize_order(amount_cents: int, description: str, custom_id: str,
                           request_id: str, return_url: str, cancel_url: str) -> dict:
    """Create an order with intent AUTHORIZE. The client approves; nothing is charged yet."""
    payload = {
        "intent": "AUTHORIZE",
        "purchase_units": [{
            "amount": {"currency_code": "USD", "value": usd(amount_cents)},
            "description": description[:127],
            "custom_id": custom_id,
        }],
        "payment_source": {"paypal": {"experience_context": {
            "brand_name": "The Guild",
            "user_action": "CONTINUE",
            "return_url": return_url,
            "cancel_url": cancel_url,
        }}},
    }
    r = httpx.post(f"{_base()}/v2/checkout/orders",
                   headers={**auth_headers(), "PayPal-Request-Id": request_id}, json=payload, timeout=30)
    r.raise_for_status()
    data = r.json()
    approve = next((l["href"] for l in data.get("links", []) if l.get("rel") in ("payer-action", "approve")), "")
    return {"order_id": data["id"], "approve_url": approve}


def get_order(order_id: str) -> dict:
    r = httpx.get(f"{_base()}/v2/checkout/orders/{order_id}", headers=auth_headers(), timeout=30)
    r.raise_for_status()
    return r.json()


def authorize_order(order_id: str) -> str:
    """Turn an approved order into a hold. Returns the authorization ID."""
    r = httpx.post(f"{_base()}/v2/checkout/orders/{order_id}/authorize",
                   headers={**auth_headers(), "PayPal-Request-Id": f"AUTH-{order_id}"}, json={}, timeout=30)
    r.raise_for_status()
    return r.json()["purchase_units"][0]["payments"]["authorizations"][0]["id"]


def capture_authorization(authorization_id: str, amount_cents: int) -> str:
    """Charge the held funds. Returns the capture ID."""
    r = httpx.post(f"{_base()}/v2/payments/authorizations/{authorization_id}/capture",
                   headers={**auth_headers(), "PayPal-Request-Id": f"CAP-{authorization_id}"},
                   json={"amount": {"currency_code": "USD", "value": usd(amount_cents)}, "final_capture": True},
                   timeout=30)
    r.raise_for_status()
    return r.json()["id"]


def void_authorization(authorization_id: str) -> None:
    r = httpx.post(f"{_base()}/v2/payments/authorizations/{authorization_id}/void",
                   headers={**auth_headers(), "PayPal-Request-Id": f"VOID-{authorization_id}"}, timeout=30)
    if r.status_code == 422:
        return  # already voided or expired
    r.raise_for_status()