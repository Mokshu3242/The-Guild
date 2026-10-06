# The Guild\backend\app\services\paypal.py
import time
import httpx

from app.config import settings

_token: str | None = None
_expires_at: float = 0.0


def _base() -> str:
    return settings.paypal_base_url


def get_access_token() -> str:
    global _token, _expires_at
    if _token and time.time() < _expires_at - 300:
        return _token

    resp = httpx.post(
        f"{_base()}/v1/oauth2/token",
        auth=(settings.paypal_client_id, settings.paypal_client_secret),
        data={"grant_type": "client_credentials"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    _token = data["access_token"]
    _expires_at = time.time() + data.get("expires_in", 3600)
    return _token


def auth_headers() -> dict:
    return {
        "Authorization": f"Bearer {get_access_token()}",
        "Content-Type": "application/json",
    }

def usd(cents: int) -> str:
    """10050 -> '100.50'. Integer math, no floats."""
    if cents < 0:
        raise ValueError("negative amount")
    return f"{cents // 100}.{cents % 100:02d}"