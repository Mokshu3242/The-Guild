from sqlmodel import Session, select

from app.models import AgentAction, Claim, Guild, Invoice, Job, Member, Milestone, Payout, PoolTx
from app.services import paypal_payouts


def pay_claim(session: Session, claim_id, admin: Member, note: str = "", override: bool = False) -> dict:
    """Pay an approved claim from the pool. Locks the claim and guild rows.

    PayPal errors are raised so the caller rolls back and nothing is recorded.
    The caller commits on success.
    """
    claim = session.exec(select(Claim).where(Claim.id == claim_id).with_for_update()).one()
    if claim.status == "paid":
        return {"status": "already_paid", "claim_id": str(claim.id)}
    if claim.status != "ai_reviewed":
        raise ValueError(f"Claim is {claim.status}, it must be AI-reviewed first")

    invoice = session.get(Invoice, claim.invoice_id)
    if invoice.status == "paid":
        raise ValueError("The client already paid this invoice")

    guild = session.exec(select(Guild).where(Guild.id == claim.guild_id).with_for_update()).one()
    member = session.get(Member, claim.member_id)
    job = session.get(Job, session.get(Milestone, invoice.milestone_id).job_id)

    amount = invoice.amount * guild.claim_cap_pct // 100
    if amount <= 0:
        raise ValueError("Claim amount is zero")
    if guild.pool_balance < amount:
        raise ValueError(
            f"The pool has ${guild.pool_balance // 100}.{guild.pool_balance % 100:02d}, "
            f"but this claim needs ${amount // 100}.{amount % 100:02d}. "
            "It refills as invoices get paid and members contribute."
        )
    if not member.paypal_email:
        raise ValueError(f"{member.name} has no PayPal email on file")

    payout = Payout(
        guild_id=guild.id,
        source_type="claim",
        source_id=claim.id,
        member_id=member.id,
        amount=amount,
        kind="claim",
    )
    session.add(payout)
    session.flush()

    batch_id = paypal_payouts.send_batch_payout(
        [{
            "receiver_email": member.paypal_email,
            "amount_cents": amount,
            "note": f"Guild safety pool covered unpaid work for {job.client_name}",
            "item_id": str(payout.id),
        }],
        batch_ref=f"CLAIM-{claim.id}",
    )

    payout.paypal_batch_id = batch_id
    payout.status = "sent"
    guild.pool_balance -= amount
    claim.status = "paid"
    claim.admin_decision = "approved"
    claim.admin_note = note
    claim.payout_id = payout.id
    session.add_all([payout, guild, claim])
    session.add(PoolTx(
        guild_id=guild.id,
        amount=amount,
        direction="out",
        source="claim_payout",
        external_ref=f"claim:{claim.id}",
    ))
    session.add(AgentAction(
        guild_id=guild.id,
        action="claim.paid",
        inputs={
            "claim_id": str(claim.id),
            "approved_by": admin.name,
            "ai_verdict": claim.ai_verdict,
            "override": override,
            "admin_note": note,
        },
        result={"amount_cents": amount, "pool_after": guild.pool_balance, "batch_id": batch_id},
    ))
    return {
        "status": "paid",
        "claim_id": str(claim.id),
        "amount_cents": amount,
        "pool_after_cents": guild.pool_balance,
        "payout_batch_id": batch_id,
    }