"""Reset The Guild to a clean demo story.

Keeps: Supabase login accounts, the PayPal subscription plan, and Sara's
real PayPal subscription (so monthly payments still reach the pool).

Seeds:
  - Design Collective with Maya (admin), Leo, Sara
  - An open job, waiting for an AI match
  - A matched job with a milestone, ready to invoice
  - A paid job, already split (history)
  - A REAL PayPal invoice to Gary Ghost ($300), 16 days unpaid, so he scores
    High risk and is ready for a claim
  - A $1,025 pool (founding $1,000 plus the paid job's slice), big enough for
    an advance and a claim in the same demo

Also keeps everyone's profile photo, and clears announcements and
maintenance windows from the platform admin.

Agreements (11B): Maya, Leo and Sara have signed the Member Pledge. Gary and
Bloom Studio accepted their work agreements. Northwind has not yet, so the
demo can show a client accepting on the client page.

Run from backend/ with the venv active:
    python -m scripts.reset_demo
"""

import secrets
import uuid
from datetime import timedelta

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from sqlmodel import Session, delete, select

from app.db import engine
from app.models import (
    Advance, AgentAction, AgentMandate, Agreement, ApiKey, Quote, Broadcast, DirectPayment, MemberDebt, Claim, Deposit, Guild, GuildDigest, Invoice, Job, MaintenanceWindow, Member,
    Milestone, Payout, PoolTx, Reminder, ScopeFlag, Subscription, WebhookEvent, utcnow,
)
from app.services.agreements import PLEDGE_VERSION, WORK_VERSION, render_pledge, render_work, sha256
from app.services import paypal_invoices

PEOPLE = {
    "maya": dict(email="maya@guild.test", name="Maya", paypal="member0-sb@personal.example.com",
                 skills=["branding", "strategy", "design"], rate=9500, role="admin", days=60),
    "leo": dict(email="leo@guild.test", name="Leo", paypal="member2-sb@personal.example.com",
                skills=["react", "tailwind", "next.js"], rate=9000, role="member", days=45),
    "sara": dict(email="sara@guild.test", name="Sara", paypal="member3-sb@personal.example.com",
                 skills=["copywriting", "seo", "content"], rate=7500, role="member", days=30),
}
# 14A: read-only admin for judges. Optional: seeded only if the Supabase login exists.
JUDGE = dict(email="judge@guild.test", name="Judge")
CLIENT_PAYS = "client1-sb@personal.example.com"
CLIENT_GHOSTS = "client2-sb@personal.example.com"
GHOST_DAYS_UNPAID = 16   # over 14 days, so the 7A rule scores Gary as High risk


def supabase_user_id(session: Session, email: str, required: bool = True):
    row = session.connection().execute(
        text("select id from auth.users where email = :e"), {"e": email}
    ).first()
    if not row and not required:
        return None
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
    # Profile photos live in Supabase Storage. Keep the links so the navbar still shows faces.
    avatars = {
        mem.email: mem.avatar_url
        for mem in session.exec(select(Member)).all()
        if getattr(mem, "avatar_url", "")
    }
    # API keys (13A) are pasted into Claude Desktop, so keep working keys across a reset.
    keys = []
    for k in session.exec(select(ApiKey).where(ApiKey.active == True)).all():  # noqa: E712
        owner = session.get(Member, k.member_id)
        if owner:
            keys.append(dict(email=owner.email, name=k.name, prefix=k.prefix, key_hash=k.key_hash))
    return {"plan_id": old_guild.paypal_plan_id if old_guild else "", "subs": subs, "avatars": avatars,
            "api_keys": keys}


def wipe(session: Session) -> None:
    # Children first, so no foreign key blocks a delete.
    for model in (AgentMandate, Quote, Advance, MemberDebt, DirectPayment, Agreement, GuildDigest, Broadcast, MaintenanceWindow, ScopeFlag, Deposit, Reminder, AgentAction,
                  Claim, Payout, PoolTx, Subscription, WebhookEvent, Invoice, Milestone, Job, ApiKey, Member, Guild):
        session.exec(delete(model))
    session.commit()


def seed(session: Session, kept: dict) -> None:
    now = utcnow()

    guild = Guild(
        name="Design Collective", invite_code=secrets.token_urlsafe(8),  # random: the repo is public
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
            avatar_url=kept.get("avatars", {}).get(p["email"], ""),
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

    # Judge account (14A): sees everything an admin sees, changes nothing
    judge_id = supabase_user_id(session, JUDGE["email"], required=False)
    if judge_id:
        session.add(Member(guild_id=guild.id, user_id=judge_id, name=JUDGE["name"], email=JUDGE["email"],
                           role="admin", read_only=True, available=False, skills=[]))

    # Restore API keys, so an agent set up before the reset keeps working
    for k in kept.get("api_keys", []):
        owner = next((mem for mem in m.values() if mem.email == k["email"] and mem.role == "admin"), None)
        if owner:
            session.add(ApiKey(guild_id=guild.id, member_id=owner.id, name=k["name"], prefix=k["prefix"],
                               key_hash=k["key_hash"]))

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
        created_at=now - timedelta(days=GHOST_DAYS_UNPAID + 4),
    )
    session.add_all([active, paid, ghost])
    session.flush()

    session.add(Milestone(job_id=active.id, title="Ordering page redesign", amount=60000, status="pending",
                          scope="Hero, cart, and checkout confirmation. Two rounds of edits."))
    paid_ms = Milestone(job_id=paid.id, title="Landing page copy", amount=50000, status="paid",
                        scope="Hero plus three product sections.",
                        delivered_at=now - timedelta(days=21), delivery_note="Final copy doc shared in Google Docs.",
                        client_approved_at=now - timedelta(days=20), approved_by="client")
    ghost_ms = Milestone(job_id=ghost.id, title="Studio website copy", amount=30000, status="invoiced",
                         scope="Home, about, and three class pages. Two rounds of edits.",
                         delivered_at=now - timedelta(days=GHOST_DAYS_UNPAID + 1),
                         delivery_note="All five pages delivered as a shared doc, plus the edits from round two.")
    session.add_all([paid_ms, ghost_ms])
    session.flush()

    # Signed agreements, so claims and the claim reviewer can see what was agreed.
    for member in m.values():
        text = render_pledge(guild, member)
        session.add(Agreement(guild_id=guild.id, member_id=member.id, kind="pledge",
                              template_version=PLEDGE_VERSION, body=text, sha256=sha256(text),
                              signer_name=member.name, signer_email=member.email, ip="seed",
                              accepted_at=member.joined_at))
    for job, ms, signer, days_ago in ((paid, [paid_ms], "Bloom Studio", 24),
                                      (ghost, [ghost_ms], "Gary Ghost", GHOST_DAYS_UNPAID + 3)):
        text = render_work(session, job, ms)
        session.add(Agreement(guild_id=guild.id, job_id=job.id, kind="work", template_version=WORK_VERSION,
                              body=text, sha256=sha256(text), milestone_ids=[str(x.id) for x in ms],
                              total_cents=sum(x.amount for x in ms), signer_name=signer,
                              signer_email=job.client_email, ip="seed",
                              accepted_at=now - timedelta(days=days_ago)))

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
        amount_cents=30000, item_name="Studio website copy", note="Milestone for Gary Ghost",
    )
    paypal_invoices.send_invoice(pp_id)
    pay_url = paypal_invoices.payer_url(paypal_invoices.get_invoice(pp_id))
    session.add(Invoice(milestone_id=ghost_ms.id, paypal_invoice_id=pp_id, pay_url=pay_url,
                        amount=30000, status="sent", sent_at=now - timedelta(days=GHOST_DAYS_UNPAID)))

    # Pool: founding contribution + the paid job's slice
    pool_entries = [
        (100000, "founding", now - timedelta(days=60)),   # $1,000, so the video can show an advance and a claim
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
    print(f"Profile photos kept: {len(kept.get('avatars', {}))}")
    print(f"API keys kept: {len(kept.get('api_keys', []))}")
    print(f"Gary Ghost invoice (unpaid, {GHOST_DAYS_UNPAID} days old): {pp_id}")


if __name__ == "__main__":
    answer = input("This deletes ALL guild data (logins stay). Type RESET to continue: ")
    if answer.strip() != "RESET":
        raise SystemExit("Cancelled.")
    with Session(engine) as session:
        kept = remember_paypal_links(session)
        wipe(session)
        seed(session, kept)
