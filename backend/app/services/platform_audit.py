"""Platform-only audit log. Separate from AgentAction so guilds never see it."""
from sqlmodel import Session, select

from app.models import PlatformAuditLog


def log(session: Session, actor_email: str, action: str, target_id: str = "",
        inputs: dict | None = None, result: dict | None = None) -> None:
    """Adds the row. The caller commits it together with the change itself."""
    session.add(PlatformAuditLog(
        actor_email=actor_email, action=action, target_id=target_id,
        inputs=inputs or {}, result=result or {},
    ))


def recent(session: Session, limit: int = 100) -> list[dict]:
    rows = session.exec(
        select(PlatformAuditLog).order_by(PlatformAuditLog.created_at.desc()).limit(limit)
    ).all()
    return [
        {"id": str(r.id), "actor_email": r.actor_email, "action": r.action, "target_id": r.target_id,
         "inputs": r.inputs, "result": r.result, "created_at": r.created_at.isoformat()}
        for r in rows
    ]
