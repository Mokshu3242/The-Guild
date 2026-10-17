from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.db import get_session
from app.deps import require_admin
from app.models import Member
from app.services.autopilot import scan

router = APIRouter(prefix="/autopilot", tags=["autopilot"])


@router.post("/scan")
def scan_actions(
    me: Member = Depends(require_admin),
    session: Session = Depends(get_session),
):
    # Admins only: the cards lead to admin actions (reminders, deposits, matching).
    result = scan(session, me)
    session.commit()
    return result