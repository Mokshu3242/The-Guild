import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlmodel import Session

from app.config import settings
from app.db import get_session
from app.services.reminders import run_all

router = APIRouter(prefix="/tasks", tags=["tasks"])


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