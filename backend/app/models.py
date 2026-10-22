from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column, DateTime, UniqueConstraint
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
    status: str = "active"   # active | maintenance | suspended
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
    avatar_url: str = ""
    role: str = "member"  # admin or member
    joined_at: datetime = created_field()
    # 14A: a judge account. Sees what an admin sees, can't change anything (enforced in deps.py).
    read_only: bool = False
    # 14B: "busy until". After this date the member counts as free again, even if available is off.
    available_from: Optional[datetime] = optional_time()


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
    client_risk: str = ""
    client_risk_reason: str = ""
    skill_coverage: str = ""
    skill_gap: dict | None = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = created_field()
    portal_token: Optional[str] = Field(default=None, index=True, unique=True)
    portal_token_created_at: Optional[datetime] = optional_time()
    # Plain-English summary of the work agreement, and the agreement text hash it was written for.
    agreement_summary: str = ""
    agreement_summary_hash: str = ""
    # 13A: how the job came in. manual, or api (a client's agent hired the guild with an API key).
    source: str = "manual"
    api_key_id: Optional[UUID] = Field(default=None, foreign_key="api_keys.id")


class Milestone(SQLModel, table=True):
    __tablename__ = "milestones"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    job_id: UUID = Field(foreign_key="jobs.id", index=True)
    title: str
    scope: str = ""
    amount: int
    due_date: Optional[datetime] = optional_time()
    status: str = "pending"
    delivered_at: Optional[datetime] = optional_time()
    delivery_note: str = ""
    client_approved_at: Optional[datetime] = optional_time()
    client_changes_requested_at: Optional[datetime] = optional_time()
    client_feedback: str = ""
    approved_by: str = ""     # "" | client | silence (no reply within the review window)
    created_at: datetime = created_field()


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
    ai_mediation_cents: int = 0
    ai_mediation_reason: str = ""
    # 12A: money that came back to the pool after the client finally paid.
    recovered_cents: int = 0
    recovered_at: Optional[datetime] = optional_time()
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

class Reminder(SQLModel, table=True):
    __tablename__ = "reminders"
    __table_args__ = (UniqueConstraint("invoice_id", "tier", name="uq_reminder_invoice_tier"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    guild_id: UUID = Field(foreign_key="guilds.id", index=True)
    invoice_id: UUID = Field(foreign_key="invoices.id", index=True)
    tier: int  # 1 friendly, 2 firm, 3 final
    subject: str = ""
    body: str = ""
    days_overdue: int = 0
    written_by: str = "ai"  # ai or template
    sent_at: Optional[datetime] = optional_time()
    created_at: datetime = created_field()
    risk_level: str = ""

class ScopeFlag(SQLModel, table=True):
    __tablename__ = "scope_flags"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    guild_id: UUID = Field(foreign_key="guilds.id", index=True)
    job_id: UUID = Field(foreign_key="jobs.id", index=True)
    client_message: str
    checked_by: str = ""
    verdict: str = "unclear"  # in_scope, out_of_scope, unclear
    reason: str = ""
    suggested_title: str = ""
    suggested_scope: str = ""
    suggested_amount_cents: int = 0
    status: str = "flagged"  # flagged, noted, added, dismissed
    addon_milestone_id: Optional[UUID] = Field(default=None, foreign_key="milestones.id")
    created_at: datetime = created_field()

class Deposit(SQLModel, table=True):
    __tablename__ = "deposits"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    guild_id: UUID = Field(foreign_key="guilds.id", index=True)
    milestone_id: UUID = Field(foreign_key="milestones.id", index=True)
    amount_cents: int
    paypal_order_id: str = Field(default="", index=True)
    paypal_authorization_id: str = Field(default="", index=True)
    paypal_capture_id: str = ""
    approve_url: str = ""
    status: str = "created"  # created, authorized, captured, voided
    requested_by: str = ""
    delivery_note: str = ""
    ai_verdict: str = ""
    ai_reason: str = ""
    authorized_at: Optional[datetime] = optional_time()
    captured_at: Optional[datetime] = optional_time()
    voided_at: Optional[datetime] = optional_time()
    created_at: datetime = created_field()

class Broadcast(SQLModel, table=True):
    __tablename__ = "broadcasts"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    guild_id: Optional[UUID] = Field(default=None, foreign_key="guilds.id", index=True)  # None = every guild
    level: str = "info"            # info | warning | critical
    title: str = ""
    body: str = ""
    starts_at: datetime = created_field()
    ends_at: Optional[datetime] = optional_time()
    created_by_email: str = ""
    created_at: datetime = created_field()


class MaintenanceWindow(SQLModel, table=True):
    __tablename__ = "maintenance_windows"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    guild_id: Optional[UUID] = Field(default=None, foreign_key="guilds.id", index=True)  # None = every guild
    mode: str = "read_only"        # read_only | full_pause
    message: str = ""
    starts_at: datetime = created_field()
    ends_at: Optional[datetime] = optional_time()
    created_by_email: str = ""
    created_at: datetime = created_field()

class PlatformSetting(SQLModel, table=True):
    __tablename__ = "platform_settings"

    key: str = Field(primary_key=True)
    value: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    updated_by_email: str = ""
    updated_at: datetime = created_field()


class PlatformAuditLog(SQLModel, table=True):
    __tablename__ = "platform_audit_log"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    actor_email: str = Field(default="", index=True)
    action: str = Field(default="", index=True)   # "broadcast.create", "guild.suspend", ...
    target_id: str = ""
    inputs: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    result: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    created_at: datetime = created_field()

class GuildDigest(SQLModel, table=True):
    __tablename__ = "guild_digests"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    guild_id: UUID = Field(foreign_key="guilds.id", index=True)
    period_start: datetime = created_field()
    period_end: datetime = created_field()
    narrative: str = ""
    stats: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    written_by: str = "ai"   # ai | template
    created_at: datetime = created_field()


class Agreement(SQLModel, table=True):
    """One accepted agreement: the exact text, its hash, and who accepted it.

    kind: work (client, first time), amendment (client, after new milestones), pledge (member).
    The text is a snapshot. It never changes after acceptance, so the hash proves what was agreed.
    """
    __tablename__ = "agreements"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    guild_id: UUID = Field(foreign_key="guilds.id", index=True)
    job_id: Optional[UUID] = Field(default=None, foreign_key="jobs.id", index=True)
    member_id: Optional[UUID] = Field(default=None, foreign_key="members.id", index=True)
    kind: str = "work"                 # work | amendment | pledge
    template_version: str = ""         # work-1, pledge-1
    body: str = ""                     # the exact text that was accepted
    sha256: str = Field(default="", index=True)
    milestone_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    total_cents: int = 0
    signer_name: str = ""
    signer_email: str = ""
    ip: str = ""
    user_agent: str = ""
    accepted_at: datetime = created_field()


class DirectPayment(SQLModel, table=True):
    """A member says the client paid them outside the guild invoice (pledge clause 4)."""
    __tablename__ = "direct_payments"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    guild_id: UUID = Field(foreign_key="guilds.id", index=True)
    invoice_id: UUID = Field(foreign_key="invoices.id", index=True)
    member_id: UUID = Field(foreign_key="members.id", index=True)
    amount_cents: int = 0          # what the member says they received
    method: str = "other"          # cash | bank | other
    note: str = ""
    status: str = "reported"       # reported | settled | rejected
    owed_cents: int = 0            # what the member owes the guild after settling
    decided_by: str = ""
    decision_note: str = ""
    created_at: datetime = created_field()
    decided_at: Optional[datetime] = optional_time()


class MemberDebt(SQLModel, table=True):
    """Money a member owes the guild. Taken from their next payouts first (set-off).

    kind: direct_payment now, advance in 12B.
    """
    __tablename__ = "member_debts"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    guild_id: UUID = Field(foreign_key="guilds.id", index=True)
    member_id: UUID = Field(foreign_key="members.id", index=True)
    kind: str = "direct_payment"
    source_id: str = ""            # the DirectPayment (or Advance) id
    amount_cents: int = 0
    repaid_cents: int = 0
    status: str = "open"           # open | repaid | written_off
    note: str = ""
    created_at: datetime = created_field()
    closed_at: Optional[datetime] = optional_time()



class Advance(SQLModel, table=True):
    """12B Paid on day one. The pool pays part of a sent invoice early.

    When the client pays, the advance plus its fee comes off the worker's share first.
    If the client hasn't paid 45 days after the advance, it becomes a MemberDebt.
    status: pending | paid | repaid | declined | defaulted | converted (client paid the member directly)
    """
    __tablename__ = "advances"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    guild_id: UUID = Field(foreign_key="guilds.id", index=True)
    invoice_id: UUID = Field(foreign_key="invoices.id", index=True)
    member_id: UUID = Field(foreign_key="members.id", index=True)
    advance_cents: int = 0
    fee_cents: int = 0
    status: str = "pending"
    explanation: str = ""          # AI or rules sentence for the admin
    explained_by: str = "rules"    # ai | rules
    decided_by: str = ""
    decision_note: str = ""
    paypal_batch_id: str = ""
    member_debt_id: Optional[UUID] = Field(default=None, foreign_key="member_debts.id")
    created_at: datetime = created_field()
    paid_at: Optional[datetime] = optional_time()
    closed_at: Optional[datetime] = optional_time()


class ApiKey(SQLModel, table=True):
    """13A. A key a client's AI agent uses to get quotes and hire the guild.

    Only the SHA-256 of the key is stored. The key itself is shown once.
    The admin who made the key is the referrer on jobs that come in through it.
    """
    __tablename__ = "api_keys"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    guild_id: UUID = Field(foreign_key="guilds.id", index=True)
    member_id: UUID = Field(foreign_key="members.id")
    name: str = ""
    prefix: str = ""
    key_hash: str = Field(index=True, unique=True)
    active: bool = True
    request_count: int = 0
    last_used_at: Optional[datetime] = optional_time()
    created_at: datetime = created_field()
    revoked_at: Optional[datetime] = optional_time()


class Quote(SQLModel, table=True):
    """13A. A priced plan made from a client's brief. Hiring means accepting a quote by id,
    so an agent can never change the prices it was given."""
    __tablename__ = "quotes"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    guild_id: UUID = Field(foreign_key="guilds.id", index=True)
    api_key_id: UUID = Field(foreign_key="api_keys.id", index=True)
    brief: str = ""
    summary: str = ""
    pricing_basis: str = ""
    budget_cents: Optional[int] = None
    milestones: list = Field(default_factory=list, sa_column=Column(JSON))
    total_cents: int = 0
    status: str = "open"            # open | hired
    job_id: Optional[UUID] = Field(default=None, foreign_key="jobs.id")
    created_at: datetime = created_field()
    expires_at: datetime = created_field()


class AgentMandate(SQLModel, table=True):
    """13B. What the agent may do on its own in one guild. No row means the defaults below.

    The daily reminder cron sends tiers up to remind_max_tier on its own (default 0: none).
    Higher tiers wait for a person. Claims and advances are off until an admin turns them on.
    Every automatic money action is credited to the admin who set the mandate (set_by_id).
    """
    __tablename__ = "agent_mandates"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    guild_id: UUID = Field(foreign_key="guilds.id", unique=True, index=True)
    active: bool = True
    remind_max_tier: int = 0          # 0 = none on their own, 1 friendly, 2 firm, 3 final
    auto_claim: bool = False
    claim_max_cents: int = 5_000
    claim_min_confidence: int = 85    # percent
    auto_advance: bool = False
    advance_max_cents: int = 5_000
    set_by_id: Optional[UUID] = Field(default=None, foreign_key="members.id")
    set_by_name: str = ""
    updated_at: datetime = created_field()
