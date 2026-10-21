import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlmodel import Session

from app.config import settings
from app.db import get_session
from app.services.auto_approve import run_auto_approve
from app.services.advances import sweep_defaults
from app.services.reminders import run_all

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _check(secret: str) -> None:
    if not settings.task_secret:
        raise HTTPException(503, "TASK_SECRET is not configured")
    if not secrets.compare_digest(secret, settings.task_secret):
        raise HTTPException(401, "Bad task secret")


@router.post("/late-invoices")
def late_invoices(
    x_task_secret: str = Header(default=""),
    session: Session = Depends(get_session),
):
    if not settings.task_secret:
        raise HTTPException(503, "TASK_SECRET is not configured")
    if not secrets.compare_digest(x_task_secret, settings.task_secret):
        raise HTTPException(401, "Bad task secret")
    results = run_all(session)
    sent = [r for r in results if r.get("status") == "sent"]
    return {"checked": len(results), "sent": len(sent), "results": results}


@router.post("/auto-approve")
def auto_approve(
    x_task_secret: str = Header(default=""),
    session: Session = Depends(get_session),
):
    """Daily cron: deliveries with no client reply in 5 business days count as approved."""
    _check(x_task_secret)
    approved = run_auto_approve(session)
    return {"approved": len(approved), "milestones": approved}



@router.post("/advance-defaults")
def advance_defaults(
    x_task_secret: str = Header(default=""),
    session: Session = Depends(get_session),
):
    """Daily cron: advances still unpaid 45 days later become a member debt."""
    _check(x_task_secret)
    done = sweep_defaults(session)
    return {"defaulted": len(done), "advances": done}
