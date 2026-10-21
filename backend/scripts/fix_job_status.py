"""One-off: recalculate every job's status from its milestones.

Fixes jobs that were marked "paid" when only their first milestone was paid.
Run from backend/ with the venv active:
    python -m scripts.fix_job_status
"""
from dotenv import load_dotenv
load_dotenv()

from sqlmodel import Session, select

from app.db import engine
from app.models import Job
from app.services.job_status import settle_job_status

if __name__ == "__main__":
    with Session(engine) as session:
        changed = 0
        for job in session.exec(select(Job)).all():
            before = job.status
            after = settle_job_status(session, job)
            if before != after:
                changed += 1
                print(f"{job.client_name}: {before} -> {after}")
        session.commit()
        print(f"Done. {changed} job(s) changed.")
