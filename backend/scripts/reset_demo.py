"""Reset The Guild to a clean demo story.

Keeps: Supabase login accounts, the PayPal subscription plan, and Sara's
real PayPal subscription (so monthly payments still reach the pool).

Seeds:
  - Design Collective with Maya (admin), Leo, Sara
  - An open job, waiting for an AI match
  - A matched job with a milestone, ready to invoice
  - A paid job, already split (history)
  - A REAL PayPal invoice to Gary Ghost, marked 10 days overdue, ready for a claim

Run from backend/ with the venv active:
    python -m scripts.reset_demo
"""

import uuid
from datetime import timedelta

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from sqlmodel import Session, delete, select

from app.db import engine
from app.models import (
    AgentAction, Claim, Guild, Invoice, Job, Member, Milestone,
    Payout, PoolTx, Subscription, WebhookEvent, utcnow,
)
from app.services import paypal_invoices

PEOPLE = {
    "maya": dict(email="maya@guild.test", name="Maya", paypal="member0-sb@personal.example.com",
                 skills=["branding", "strategy", "design"], rate=9500, role="admin", days=60),
    "leo": dict(email="leo@guild.test", name="Leo", paypal="member2-sb@personal.example.com",
                skills=["react", "tailwind", "next.js"], rate=9000, role="member", days=45),
    "sara": dict(email="sara@guild.test", name="Sara", paypal="member3-sb@personal.example.com",
                 skills=["copywriting", "seo", "content"], rate=7500, role="member", days=30),
}
CLIENT_PAYS = "client1-sb@personal.example.com"
CLIENT_GHOSTS = "client2-sb@personal.example.com"


def supabase_user_id(session: Session, email: str):
    row = session.connection().execute(
        text("select id from auth.users where email = :e"), {"e": email}
    ).first()
    if not row:
        raise SystemExit(f"No Supabase login for {email}. Create it in Authentication → Users first.")
    return row[0]


def remember_paypal_links(session: Session) -> dict:
    """Save what lives in PayPal so we don't orphan it."""
    old_guild = session.exec(select(Guild)).first()
    subs = []
    for sub in session.exec(select(Subscription).where(Subscription.status.in_(["active", "pending"]))).all():
        member = session.get(Member, sub.member_id)
        if member:
            subs.append(dict(email=member.email, paypal_id=sub.paypal_subscription_id,
                             status=sub.status, approve_url=sub.approve_url, activated_at=sub.activated_at))
    return {"plan_id": old_guild.paypal_plan_id if old_guild else "", "subs": subs}


def wipe(session: Session) -> None:
    for model in (AgentAction, Claim, Payout, PoolTx, Subscription, WebhookEvent,
                  Invoice, Milestone, Job, Member, Guild):
        session.exec(delete(model))
    session.commit()


def seed(session: Session, kept: dict) -> None:
    now = utcnow()

    guild = Guild(
        name="Design Collective", invite_code="DESIGN2026",
        worker_pct=85, referrer_pct=10, pool_pct=5,
        monthly_fee=1000, claim_wait_days=3, claim_overdue_days=7, claim_cap_pct=50,
        paypal_plan_id=kept["plan_id"],
        created_at=now - timedelta(days=60),
    )
    session.add(guild)
    session.flush()

    m = {}
    for key, p in PEOPLE.items():
        m[key] = Member(
            guild_id=guild.id, user_id=supabase_user_id(session, p["email"]),
            name=p["name"], email=p["email"], paypal_email=p["paypal"],
            skills=p["skills"], hourly_rate_cents=p["rate"], available=True,
            role=p["role"], joined_at=now - timedelta(days=p["days"]),
        )
    session.add_all(m.values())
    session.flush()

    # Restore real PayPal subscriptions
    for s in kept["subs"]:
        owner = next((mem for mem in m.values() if mem.email == s["email"]), None)
        if owner:
            session.add(Subscription(
                guild_id=guild.id, member_id=owner.id, paypal_subscription_id=s["paypal_id"],
                status=s["status"], approve_url=s["approve_url"], activated_at=s["activated_at"],
            ))

    # Job 1: open, waiting for the AI
    session.add(Job(
        guild_id=guild.id, referrer_id=m["maya"].id,
        client_name="Anna Startup", client_email=CLIENT_PAYS, status="open",
        description="Build a React and Tailwind marketing site from a finished Figma design. "
                    "Four sections, mobile first, two week timeline.",
        created_at=now - timedelta(hours=3),
    ))

    # Job 2: matched to Leo, milestone ready to invoice
    active = Job(
        guild_id=guild.id, referrer_id=m["maya"].id, worker_id=m["leo"].id,
        client_name="Northwind Coffee", client_email=CLIENT_PAYS, status="matched",
        description="Redesign the online ordering page. Keep the existing API, refresh the UI and cart flow.",
        match_reason="Leo is the strongest React fit, is available now, and his rate fits the budget.",
        created_at=now - timedelta(days=2),
    )

    # Job 3: paid and split (history)
    paid = Job(
        guild_id=guild.id, referrer_id=m["maya"].id, worker_id=m["sara"].id,
        client_name="Bloom Studio", client_email=CLIENT_PAYS, status="paid",
        description="Landing page copy for a boutique skincare brand. Hero plus three product sections.",
        match_reason="Sara writes conversion copy and has done beauty brands before.",
        created_at=now - timedelta(days=25),
    )

    # Job 4: Gary Ghost never paid. Ready for a claim.
    ghost = Job(
        guild_id=guild.id, referrer_id=m["leo"].id, worker_id=m["sara"].id,
        client_name="Gary Ghost", client_email=CLIENT_GHOSTS, status="in_progress",
        description="Website copy for a fitness studio: home, about, and three class pages.",
        match_reason="Sara is the guild's copywriter and was free that week.",
        created_at=now - timedelta(days=14),
    )
    session.add_all([active, paid, ghost])
    session.flush()

    session.add(Milestone(job_id=active.id, title="Ordering page redesign", amount=60000, status="pending",
                          scope="Hero, cart, and checkout confirmation. Two rounds of edits."))
    paid_ms = Milestone(job_id=paid.id, title="Landing page copy", amount=50000, status="paid",
                        scope="Hero plus three product sections.")
    ghost_ms = Milestone(job_id=ghost.id, title="Studio website copy", amount=8000, status="invoiced",
                         scope="Home, about, and three class pages. Two rounds of edits.")
    session.add_all([paid_ms, ghost_ms])
    session.flush()

    # History: the paid invoice and its split
    paid_inv = Invoice(milestone_id=paid_ms.id, paypal_invoice_id="SEEDED-HISTORY", amount=50000,
                       status="paid", sent_at=now - timedelta(days=20), paid_at=now - timedelta(days=15))
    session.add(paid_inv)
    session.flush()
    session.add_all([
        Payout(guild_id=guild.id, source_type="invoice", source_id=paid_inv.id, member_id=m["sara"].id,
               amount=42500, kind="work", paypal_batch_id="SEEDED-HISTORY", status="completed",
               created_at=now - timedelta(days=15)),
        Payout(guild_id=guild.id, source_type="invoice", source_id=paid_inv.id, member_id=m["maya"].id,
               amount=5000, kind="referral", paypal_batch_id="SEEDED-HISTORY", status="completed",
               created_at=now - timedelta(days=15)),
    ])

    # A REAL PayPal invoice for the ghost job, then backdate it
    print("Creating a real PayPal invoice to Gary Ghost...")
    pp_id = paypal_invoices.create_invoice(
        invoice_number=f"GUILD-{uuid.uuid4().hex[:12]}", client_email=CLIENT_GHOSTS,
        amount_cents=8000, item_name="Studio website copy", note="Milestone for Gary Ghost",
    )
    paypal_invoices.send_invoice(pp_id)
    pay_url = paypal_invoices.payer_url(paypal_invoices.get_invoice(pp_id))
    session.add(Invoice(milestone_id=ghost_ms.id, paypal_invoice_id=pp_id, pay_url=pay_url,
                        amount=8000, status="sent", sent_at=now - timedelta(days=10)))

    # Pool: founding contribution + the paid job's slice
    pool_entries = [
        (5000, "founding", now - timedelta(days=60)),
        (2500, "referral_slice", now - timedelta(days=15)),
    ]
    for amount, source, when in pool_entries:
        session.add(PoolTx(guild_id=guild.id, amount=amount, direction="in", source=source, created_at=when))
    guild.pool_balance = sum(a for a, _, _ in pool_entries)
    session.add(guild)

    # Agent log
    session.add_all([
        AgentAction(guild_id=guild.id, action="job.match", created_at=now - timedelta(days=2),
                    inputs={"job_id": str(active.id)},
                    result={"top_name": "Leo", "backup_name": "Sara", "reason": active.match_reason}),
        AgentAction(guild_id=guild.id, action="invoice.paid.split", created_at=now - timedelta(days=15),
                    inputs={"invoice_id": str(paid_inv.id), "amount": 50000},
                    result={"worker_cents": 42500, "referrer_cents": 5000, "pool_cents": 2500,
                            "recovered_cents": 0, "payout_batch_id": "SEEDED-HISTORY"}),
    ])

    session.commit()
    print(f"\nSeeded {guild.name}. Invite code: {guild.invite_code}")
    print(f"Pool: ${guild.pool_balance // 100}.{guild.pool_balance % 100:02d}")
    print(f"Plan kept: {bool(kept['plan_id'])}. Subscriptions restored: {len(kept['subs'])}")
    print(f"Gary Ghost invoice (unpaid, 10 days old): {pp_id}")


if __name__ == "__main__":
    answer = input("This deletes ALL guild data (logins stay). Type RESET to continue: ")
    if answer.strip() != "RESET":
        raise SystemExit("Cancelled.")
    with Session(engine) as session:
        kept = remember_paypal_links(session)
        wipe(session)
        seed(session, kept)