from datetime import datetime, timedelta, timezone

import httpx

from app.services.paypal import _base, auth_headers, usd


def create_product(name: str) -> str:
    r = httpx.post(
        f"{_base()}/v1/catalogs/products",
        headers=auth_headers(),
        json={
            "name": name[:127],
            "description": "Guild safety pool membership",
            "type": "SERVICE",
            "category": "SOFTWARE",
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["id"]


def create_plan(product_id: str, name: str, monthly_cents: int) -> str:
    r = httpx.post(
        f"{_base()}/v1/billing/plans",
        headers={**auth_headers(), "Prefer": "return=representation"},
        json={
            "product_id": product_id,
            "name": name[:127],
            "description": "Monthly contribution to the guild safety pool",
            "status": "ACTIVE",
            "billing_cycles": [
                {
                    "frequency": {"interval_unit": "MONTH", "interval_count": 1},
                    "tenure_type": "REGULAR",
                    "sequence": 1,
                    "total_cycles": 0,
                    "pricing_scheme": {
                        "fixed_price": {"value": usd(monthly_cents), "currency_code": "USD"}
                    },
                }
            ],
            "payment_preferences": {
                "auto_bill_outstanding": True,
                "payment_failure_threshold": 3,
            },
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["id"]


def create_subscription(plan_id: str, custom_id: str, return_url: str, cancel_url: str) -> dict:
    """Returns {'id': ..., 'approve_url': ...}."""
    r = httpx.post(
        f"{_base()}/v1/billing/subscriptions",
        headers={**auth_headers(), "PayPal-Request-Id": f"SUB-{custom_id}-{plan_id}"},
        json={
            "plan_id": plan_id,
            "custom_id": custom_id,
            "application_context": {
                "brand_name": "The Guild",
                "user_action": "SUBSCRIBE_NOW",
                "return_url": return_url,
                "cancel_url": cancel_url,
            },
        },
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    approve = next((l["href"] for l in data.get("links", []) if l.get("rel") == "approve"), "")
    return {"id": data["id"], "approve_url": approve}


def get_subscription(subscription_id: str) -> dict:
    r = httpx.get(
        f"{_base()}/v1/billing/subscriptions/{subscription_id}",
        headers=auth_headers(),
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def list_transactions(subscription_id: str, days: int = 45) -> list[dict]:
    end = datetime.now(timezone.utc) + timedelta(days=1)
    start = end - timedelta(days=days)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    r = httpx.get(
        f"{_base()}/v1/billing/subscriptions/{subscription_id}/transactions",
        headers=auth_headers(),
        params={"start_time": start.strftime(fmt), "end_time": end.strftime(fmt)},
        timeout=30,
    )
    if r.status_code == 404:
        return []  # no transactions yet, e.g. still pending
    r.raise_for_status()
    return r.json().get("transactions", []) 


def cancel_subscription(subscription_id: str, reason: str = "Member left the pool") -> None:
    r = httpx.post(
        f"{_base()}/v1/billing/subscriptions/{subscription_id}/cancel",
        headers=auth_headers(),
        json={"reason": reason[:127]},
        timeout=30,
    )
    if r.status_code not in (204, 422):  # 422 = already cancelled
        r.raise_for_status()