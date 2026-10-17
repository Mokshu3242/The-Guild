from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.models import Guild, Invoice, Job, Milestone, Reminder
from app.services.ai import AIError, run_ai_json

from app.prompts import REMINDER as SYSTEM, REMINDER_TIER_TONE as TIER_TONE, REMINDER_RISK_NOTE as RISK_NOTE


class ReminderDraft(BaseModel):
    subject: str = Field(min_length=3, max_length=120)
    body: str = Field(min_length=20, max_length=1200)

FALLBACK = {
    1: ("Friendly reminder: invoice for {milestone}",
        "Hi {client}, a quick reminder that the invoice for {milestone} ({amount}) was sent {days} days ago "
        "and is still open. You can pay it any time from the PayPal link in the original invoice. "
        "Thank you! The {guild} guild"),
    2: ("Payment reminder: {milestone} is {days} days overdue",
        "Hi {client}, the invoice for {milestone} ({amount}) is now {days} days overdue. "
        "Please arrange payment within the next 5 days using the PayPal link in the invoice. "
        "If anything is holding it up, just reply and let us know. The {guild} guild"),
    3: ("Final notice: invoice for {milestone}",
        "Hi {client}, this is a final notice for the invoice for {milestone} ({amount}), now {days} days overdue. "
        "If payment isn't received within 7 days, the guild will move it to our unpaid-work process. "
        "We'd much rather settle it with you directly. The {guild} guild"),
}


def write_reminder(
    session: Session,
    invoice: Invoice,
    tier: int,
    days: int,
    risk_level: str = "unknown",
) -> tuple[ReminderDraft, str]:
    """Returns (draft, written_by). Falls back to a template if the AI fails."""
    milestone = session.get(Milestone, invoice.milestone_id)
    job = session.get(Job, milestone.job_id)
    guild = session.get(Guild, job.guild_id)

    facts = dict(
        client=job.client_name,
        milestone=milestone.title,
        days=days,
        guild=guild.name,
        amount=f"${invoice.amount // 100:,}.{invoice.amount % 100:02d}",
    )

    prior = session.exec(
        select(Reminder).where(Reminder.invoice_id == invoice.id).order_by(Reminder.tier)
    ).all()
    prior_line = (
        ", ".join(f"tier {r.tier} sent at {r.days_overdue} days" for r in prior)
        if prior
        else "none, this is the first reminder on this invoice"
    )

    level = risk_level if risk_level in RISK_NOTE else "unknown"

    prompt = (
        f"Tier: {tier} of 3\n"
        f"Tone for this tier: {TIER_TONE[tier]}\n"
        f"Client risk level: {level}\n"
        f"How to read the risk: {RISK_NOTE[level]}\n\n"
        f"Client: {facts['client']}\n"
        f"Milestone: {facts['milestone']}\n"
        f"Amount: {facts['amount']}\n"
        f"Days since the invoice was sent: {days}\n"
        f"Guild name: {facts['guild']}\n"
        f"Previous reminders on this invoice: {prior_line}"
    )

    try:
        draft = run_ai_json(
            [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
            schema=ReminderDraft,
            temperature=0.4,
            max_tokens=500,
        )
        if "[" in draft.body or "[" in draft.subject:
            raise AIError("placeholder in draft")
        return draft, "ai"
    except AIError:
        subject, body = FALLBACK[tier]
        return (
            ReminderDraft(subject=subject.format(**facts), body=body.format(**facts)),
            "template",
        )