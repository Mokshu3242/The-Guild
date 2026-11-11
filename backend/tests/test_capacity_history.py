from datetime import timedelta
from uuid import uuid4

from sqlmodel import Session, SQLModel, create_engine

from app.models import Guild, Job, Member, Milestone, utcnow
from app.services.capacity import guild_capacity


def _setup():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_history_shows_past_work_and_keeps_bookings():
    s = _setup()
    now = utcnow()
    g = Guild(name="Test guild", invite_code="TEST01")
    s.add(g)
    s.flush()
    sara = Member(guild_id=g.id, name="Sara", email="s@x.test", user_id=uuid4())
    s.add(sara)
    s.flush()
    paid = Job(guild_id=g.id, referrer_id=sara.id, worker_id=sara.id, client_name="Bloom",
               client_email="b@x.test", description="x", status="paid", created_at=now - timedelta(days=25))
    old = Job(guild_id=g.id, referrer_id=sara.id, worker_id=sara.id, client_name="Ancient",
              client_email="a@x.test", description="x", status="paid", created_at=now - timedelta(days=200))
    live = Job(guild_id=g.id, referrer_id=sara.id, worker_id=sara.id, client_name="Lena",
               client_email="l@x.test", description="x", status="in_progress", created_at=now - timedelta(days=2))
    s.add_all([paid, old, live])
    s.flush()
    s.add_all([
        Milestone(job_id=paid.id, title="a", amount=40000, status="paid", delivered_at=now - timedelta(days=21)),
        Milestone(job_id=old.id, title="a", amount=1000, status="paid", delivered_at=now - timedelta(days=190)),
        Milestone(job_id=live.id, title="a", amount=48000),
    ])
    s.commit()

    cap = guild_capacity(s, g.id, weeks=4, past_weeks=6)
    row = cap["members"][0]
    assert cap["days"] == 70
    assert [h["client"] for h in row["history"]] == ["Bloom"]   # too-old work is left out
    h = row["history"][0]
    assert h["outcome"] == "paid" and h["work_cents"] == 40000 and h["start"] <= h["end"]
    assert [b["client"] for b in row["bookings"]] == ["Lena"]   # future bookings unchanged

    plain = guild_capacity(s, g.id)   # old callers: same shape as before, no history
    assert plain["days"] == 14 and plain["members"][0]["history"] == []
