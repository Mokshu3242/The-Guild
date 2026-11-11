"""Shared test setup: a throwaway in-memory database with one small guild. No PayPal, no AI, no network."""
import os

# app.db builds a Postgres engine on import. It never connects in tests, but it needs a Postgres-style URL.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")

from datetime import timedelta
from uuid import uuid4

import pytest  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine

from app.models import Guild, Invoice, Job, Member, Milestone, utcnow
from app.services import platform_settings


@pytest.fixture
def session():
    platform_settings.clear_cache()   # kill switches are cached per process
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
    platform_settings.clear_cache()


class World:
    """Maya (admin) and Sara (member) in one guild, with helpers to add jobs and invoices."""

    def __init__(self, s: Session, pool_cents: int = 100_000):
        self.s = s
        self.guild = Guild(name="Test guild", invite_code=f"T{uuid4().hex[:6]}", pool_balance=pool_cents)
        s.add(self.guild)
        s.flush()
        self.maya = self.member("Maya", role="admin")
        self.sara = self.member("Sara")

    def member(self, name: str, role: str = "member") -> Member:
        m = Member(guild_id=self.guild.id, user_id=uuid4(), name=name, email=f"{name.lower()}@x.test",
                   paypal_email=f"{name.lower()}-pp@x.test", role=role, joined_at=utcnow() - timedelta(days=60))
        self.s.add(m)
        self.s.flush()
        return m

    def invoice(self, cents: int, worker: Member | None = None, referrer: Member | None = None,
                status: str = "sent") -> tuple[Job, Invoice]:
        worker = worker or self.sara
        job = Job(guild_id=self.guild.id, referrer_id=(referrer or worker).id, worker_id=worker.id,
                  client_name="Gary Ghost", client_email="gary@x.test", description="Website copy",
                  status="in_progress")
        self.s.add(job)
        self.s.flush()
        ms = Milestone(job_id=job.id, title="Homepage", amount=cents, delivered_at=utcnow() - timedelta(days=20))
        self.s.add(ms)
        self.s.flush()
        inv = Invoice(milestone_id=ms.id, amount=cents, status=status, sent_at=utcnow() - timedelta(days=20))
        self.s.add(inv)
        self.s.flush()
        return job, inv


@pytest.fixture
def world(session):
    return World(session)
