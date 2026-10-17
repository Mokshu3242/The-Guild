"""Platform health check: is the database, PayPal, and the AI reachable right now?

Run on demand from /platform/. Returns only ok/latency/timestamps, never money.
PayPal and the AI are checked at the same time, so one slow service doesn't
make the whole check slow.
"""
import logging
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
from sqlalchemy import text
from sqlmodel import Session, select

from app.models import AgentAction, WebhookEvent, utcnow
from app.services.ai import run_ai
from app.services.paypal import _base, auth_headers

logger = logging.getLogger(__name__)

SLOW_MS = {"db": 1500, "paypal": 4000, "ai": 15000}
WEBHOOK_QUIET_HOURS = 48     # sandbox can be quiet; this is a nudge, not an alarm
REMINDER_QUIET_DAYS = 3


def _ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def _state(ok: bool, ms: int, key: str) -> str:
    if not ok:
        return "down"
    return "slow" if ms > SLOW_MS[key] else "ok"


def _check_db(session: Session) -> dict:
    start = time.perf_counter()
    try:
        session.connection().execute(text("select 1"))
        ms = _ms(start)
        return {"state": _state(True, ms, "db"), "latency_ms": ms}
    except Exception as e:
        logger.exception("DB health check failed")
        return {"state": "down", "error": type(e).__name__}


def _check_paypal() -> dict:
    """Gets a token and lists webhooks. Proves the credentials and the API both work."""
    start = time.perf_counter()
    try:
        r = httpx.get(f"{_base()}/v1/notifications/webhooks", headers=auth_headers(), timeout=8)
        ms = _ms(start)
        if r.status_code != 200:
            return {"state": "down", "latency_ms": ms, "error": f"PayPal answered {r.status_code}"}
        return {"state": _state(True, ms, "paypal"), "latency_ms": ms}
    except Exception as e:
        logger.exception("PayPal health check failed")
        return {"state": "down", "error": type(e).__name__}


def _check_ai() -> dict:
    start = time.perf_counter()
    try:
        run_ai([{"role": "user", "content": "Reply with the single word ok."}], temperature=0.0, max_tokens=5)
        ms = _ms(start)
        return {"state": _state(True, ms, "ai"), "latency_ms": ms}
    except Exception as e:
        logger.exception("AI health check failed")
        return {"state": "down", "error": type(e).__name__}


def _when(row) -> object:
    return getattr(row, "received_at", None) or getattr(row, "created_at", None)


def _check_webhooks(session: Session) -> dict:
    """Informational: when did PayPal last talk to us?"""
    order_col = getattr(WebhookEvent, "received_at", None) or getattr(WebhookEvent, "created_at")
    last = session.exec(select(WebhookEvent).order_by(order_col.desc())).first()
    at = _when(last) if last else None
    if not at:
        return {"state": "none", "last_at": None}
    hours = (utcnow() - at).total_seconds() / 3600
    return {
        "state": "ok" if hours < WEBHOOK_QUIET_HOURS else "quiet",
        "last_at": at.isoformat(),
        "last_type": getattr(last, "event_type", None) or getattr(last, "type", None),
    }


def _check_reminders(session: Session) -> dict:
    """Informational: no reminders can simply mean nobody is late."""
    last = session.exec(
        select(AgentAction.created_at)
        .where(AgentAction.action == "reminder.sent")
        .order_by(AgentAction.created_at.desc())
    ).first()
    if not last:
        return {"state": "none", "last_at": None}
    days = (utcnow() - last).total_seconds() / 86400
    return {"state": "ok" if days < REMINDER_QUIET_DAYS else "quiet", "last_at": last.isoformat()}


def run_health_checks(session: Session) -> dict:
    with ThreadPoolExecutor(max_workers=2) as pool:
        paypal_f = pool.submit(_check_paypal)
        ai_f = pool.submit(_check_ai)
        db = _check_db(session)            # DB uses this request's session, so it stays on this thread
        webhooks = _check_webhooks(session)
        reminders = _check_reminders(session)
        paypal, ai = paypal_f.result(), ai_f.result()

    core = [db["state"], paypal["state"], ai["state"]]
    if "down" in core:
        overall = "down" if db["state"] == "down" or core.count("down") >= 2 else "degraded"
    elif "slow" in core:
        overall = "slow"
    else:
        overall = "healthy"

    return {
        "overall": overall,
        "checks": {"db": db, "paypal": paypal, "ai": ai, "webhooks": webhooks, "reminders": reminders},
        "ran_at": utcnow().isoformat(),
    }
