"""One place that decides a job's status from its milestones.

A job is "paid" only when every milestone is settled, not when the first one is.
Call it after money moves (invoice paid, deposit captured, claim paid or rejected,
new invoice sent). The caller commits.
"""
from sqlmodel import Session, select

from app.models import Claim, Invoice, Job, Milestone

OPEN_CLAIM = ("submitted", "ai_reviewed")


def settle_job_status(session: Session, job: Job) -> str:
    milestones = session.exec(select(Milestone).where(Milestone.job_id == job.id)).all()
    if not milestones:
        return job.status

    invoices = session.exec(
        select(Invoice).where(Invoice.milestone_id.in_([m.id for m in milestones]))
    ).all()
    invoice_ids = [i.id for i in invoices]
    claims = session.exec(select(Claim).where(Claim.invoice_id.in_(invoice_ids))).all() if invoice_ids else []

    # A claim waiting for a decision keeps the job flagged, whatever else happens.
    if any(c.status in OPEN_CLAIM for c in claims):
        job.status = "disputed"
        session.add(job)
        return job.status

    covered_invoices = {c.invoice_id for c in claims if c.status == "paid"}
    covered_milestones = {i.milestone_id for i in invoices if i.id in covered_invoices}
    invoiced = {i.milestone_id for i in invoices if i.status in ("sent", "paid")}

    def settled(m: Milestone) -> str | None:
        if m.status == "paid":
            return "paid"
        if m.id in covered_milestones:
            return "covered"
        return None

    states = [settled(m) for m in milestones]
    if all(states):
        job.status = "covered" if "covered" in states else "paid"
    elif any(states) or invoiced or any(m.delivered_at for m in milestones):
        job.status = "in_progress"
    # Otherwise the job hasn't really started: keep open or matched as it is.

    session.add(job)
    return job.status
