"""Platform kill switches. Stored in the DB, cached for 10 seconds per process."""
import time
from typing import Any

from sqlmodel import Session

from app.models import PlatformSetting, utcnow

TTL = 10.0
FEATURES = {"match", "scope", "claim", "reminder", "deposit_review", "risk", "autopilot", "rate", "forecast", "digest"}

_cache: dict[str, tuple[Any, float]] = {}


def _get(session: Session, key: str, default: dict) -> dict:
    hit = _cache.get(key)
    if hit and time.monotonic() < hit[1]:
        return hit[0]
    row = session.get(PlatformSetting, key)
    value = row.value if row and isinstance(row.value, dict) else default
    _cache[key] = (value, time.monotonic() + TTL)
    return value


def _set(session: Session, key: str, value: dict, by_email: str) -> None:
    row = session.get(PlatformSetting, key)
    if row:
        row.value = value
        row.updated_by_email = by_email
        row.updated_at = utcnow()
    else:
        row = PlatformSetting(key=key, value=value, updated_by_email=by_email)
    session.add(row)
    _cache.pop(key, None)   # re-read after commit, never trust an uncommitted value


def clear_cache() -> None:
    _cache.clear()


# ---------- Read by the app ----------

def ai_enabled(session: Session) -> bool:
    return bool(_get(session, "ai_enabled", {"on": True}).get("on", True))


def disabled_features(session: Session) -> list[str]:
    return list(_get(session, "ai_disabled_features", {"list": []}).get("list") or [])


def ai_feature_disabled(session: Session, feature: str) -> bool:
    return feature in disabled_features(session)


def reminders_enabled(session: Session) -> bool:
    return bool(_get(session, "reminders_enabled", {"on": True}).get("on", True))


# ---------- Written by /platform/settings ----------

def set_ai_enabled(session: Session, on: bool, by_email: str) -> None:
    _set(session, "ai_enabled", {"on": on}, by_email)


def set_reminders_enabled(session: Session, on: bool, by_email: str) -> None:
    _set(session, "reminders_enabled", {"on": on}, by_email)


def set_disabled_features(session: Session, features: list[str], by_email: str) -> list[str]:
    cleaned = sorted({f.strip() for f in features if f.strip() in FEATURES})
    _set(session, "ai_disabled_features", {"list": cleaned}, by_email)
    return cleaned


def all_settings(session: Session) -> dict:
    return {
        "ai_enabled": ai_enabled(session),
        "reminders_enabled": reminders_enabled(session),
        "ai_disabled_features": disabled_features(session),
    }
