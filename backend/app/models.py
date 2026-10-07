from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column, DateTime
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def created_field():
    return Field(default_factory=utcnow, sa_type=DateTime(timezone=True))


def optional_time():
    return Field(default=None, sa_type=DateTime(timezone=True))


# All money is stored as integer cents. Percentages are whole numbers.


class Guild(SQLModel, table=True):
    __tablename__ = "guilds"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str
    invite_code: str = Field(index=True, unique=True)
    pool_balance: int = 0
    worker_pct: int = 85
    referrer_pct: int = 10
    pool_pct: int = 5
    monthly_fee: int = 1000
    claim_wait_days: int = 14      # days a member must be in the guild
    claim_overdue_days: int = 14   # days an invoice must be overdue
    claim_cap_pct: int = 50
    paypal_plan_id: str = ""
    created_at: datetime = created_field()


class Member(SQLModel, table=True):
    __tablename__ = "members"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    guild_id: UUID = Field(foreign_key="guilds.id", index=True)
    user_id: UUID = Field(index=True, unique=True)  # Supabase auth user id
    name: str
    email: str
    paypal_email: str = ""
    skills: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    hourly_rate_cents: int = 0
    available: bool = True
    role: str = "member"  # admin or member
    joined_at: datetime = created_field()


class Job(SQLModel, table=True):
    __tablename__ = "jobs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    guild_id: UUID = Field(foreign_key="guilds.id", index=True)
    referrer_id: UUID = Field(foreign_key="members.id")
    worker_id: Optional[UUID] = Field(default=None, foreign_key="members.id")
    client_name: str
    client_email: str
    description: str
    status: str = "open"  # open, matched, in_progress, delivered, paid, disputed
    match_reason: str = ""
    created_at: datetime = created_field()


class Milestone(SQLModel, table=True):
    __tablename__ = "milestones"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    job_id: UUID = Field(foreign_key="jobs.id", index=True)
    title: str
    scope: str = ""
    amount: int
    due_date: Optional[datetime] = optional_time()
    status: str = "pending"


class Invoice(SQLModel, table=True):
    __tablename__ = "invoices"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    milestone_id: UUID = Field(foreign_key="milestones.id", index=True)
    paypal_invoice_id: str = Field(default="", index=True)
    pay_url: str = ""
    amount: int
    status: str = "draft"  # draft, sent, paid, cancelled
    sent_at: Optional[datetime] = optional_time()
    paid_at: Optional[datetime] = optional_time()


class Payout(SQLModel, table=True):
    __tablename__ = "payouts"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    guild_id: UUID = Field(foreign_key="guilds.id", index=True)
    source_type: str  # invoice or claim
    source_id: UUID
    member_id: UUID = Field(foreign_key="members.id", index=True)
    amount: int
    kind: str  # work, referral, claim
    paypal_batch_id: str = ""
    status: str = "pending"
    created_at: datetime = created_field()


class PoolTx(SQLModel, table=True):
    __tablename__ = "pool_tx"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    guild_id: UUID = Field(foreign_key="guilds.id", index=True)
    amount: int
    direction: str  # in or out
    source: str  # subscription, referral_slice, claim_payout, recovery
    external_ref: Optional[str] = Field(default=None, unique=True)
    created_at: datetime = created_field()


class Subscription(SQLModel, table=True):
    __tablename__ = "subscriptions"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    guild_id: UUID = Field(foreign_key="guilds.id", index=True)
    member_id: UUID = Field(foreign_key="members.id", index=True)
    paypal_subscription_id: str = Field(default="", index=True)
    approve_url: str = ""
    status: str = "pending"  # pending, active, suspended, cancelled
    activated_at: Optional[datetime] = optional_time()
    created_at: datetime = created_field()


class Claim(SQLModel, table=True):
    __tablename__ = "claims"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    guild_id: UUID = Field(foreign_key="guilds.id", index=True)
    member_id: UUID = Field(foreign_key="members.id")
    invoice_id: UUID = Field(foreign_key="invoices.id", index=True)
    statement: str = ""
    evidence_urls: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    status: str = "submitted"  # submitted, ai_reviewed, rejected, paid
    ai_verdict: str = ""
    ai_reason: str = ""
    ai_confidence: float = 0.0
    admin_decision: str = "pending"
    admin_note: str = ""
    payout_id: Optional[UUID] = Field(default=None, foreign_key="payouts.id")
    created_at: datetime = created_field()


class WebhookEvent(SQLModel, table=True):
    __tablename__ = "webhook_events"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    paypal_event_id: str = Field(index=True, unique=True)
    type: str
    received_at: datetime = created_field()
    processed: bool = False


class AgentAction(SQLModel, table=True):
    __tablename__ = "agent_actions"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    guild_id: Optional[UUID] = Field(default=None, foreign_key="guilds.id", index=True)
    action: str
    inputs: dict = Field(default_factory=dict, sa_column=Column(JSON))
    result: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = created_field()