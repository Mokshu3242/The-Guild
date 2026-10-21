"""13A API keys. Only the SHA-256 is stored, so a leaked database doesn't leak keys."""
import hashlib
import secrets

from sqlmodel import Session, select

from app.models import AgentAction, ApiKey, Member, utcnow

PREFIX = "guild_"


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def create(session: Session, admin: Member, name: str) -> tuple[ApiKey, str]:
    """Returns (row, the key). The key is shown once and never stored."""
    raw = PREFIX + secrets.token_urlsafe(32)
    key = ApiKey(guild_id=admin.guild_id, member_id=admin.id, name=name.strip()[:80], prefix=raw[:12],
                 key_hash=_hash(raw))
    session.add(key)
    session.flush()
    session.add(AgentAction(
        guild_id=admin.guild_id,
        action="api_key.created",
        inputs={"by": admin.name, "key_id": str(key.id)},
        result={"name": key.name, "prefix": key.prefix},
    ))
    return key, raw


def revoke(session: Session, key: ApiKey, admin: Member) -> None:
    key.active, key.revoked_at = False, utcnow()
    session.add(key)
    session.add(AgentAction(
        guild_id=key.guild_id,
        action="api_key.revoked",
        inputs={"by": admin.name, "key_id": str(key.id)},
        result={"name": key.name, "prefix": key.prefix},
    ))


def resolve(session: Session, raw: str) -> ApiKey | None:
    raw = (raw or "").strip()
    if not raw.startswith(PREFIX):
        return None
    key = session.exec(select(ApiKey).where(ApiKey.key_hash == _hash(raw))).first()
    return key if key and key.active else None


def row(k: ApiKey) -> dict:
    return {"id": str(k.id), "name": k.name, "prefix": k.prefix, "active": k.active,
            "request_count": k.request_count, "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
            "created_at": k.created_at.isoformat()}
