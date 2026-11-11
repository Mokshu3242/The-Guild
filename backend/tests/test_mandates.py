"""13B Agent mandate: the agent may only pay a claim or an advance inside the limits an admin set."""
import pytest

from app.models import Advance, AgentAction, AgentMandate, Claim, PlatformSetting
from app.services import mandates, platform_settings
from app.services.claim_reviewer import claim_cap_cents


def _mandate(world, **kw):
    m = AgentMandate(guild_id=world.guild.id, active=True, auto_claim=True, auto_advance=True,
                     set_by_id=world.maya.id, set_by_name="Maya", **kw)
    world.s.add(m)
    world.s.flush()
    return m


def _claim(world, invoice_cents=8_000, verdict="approve", confidence=0.92, reason="Delivered and approved"):
    _, inv = world.invoice(invoice_cents)
    c = Claim(guild_id=world.guild.id, member_id=world.sara.id, invoice_id=inv.id, status="ai_reviewed",
              ai_verdict=verdict, ai_confidence=confidence, ai_reason=reason)
    world.s.add(c)
    world.s.flush()
    return c


def test_claim_cap_is_half_the_invoice(world):
    c = _claim(world, invoice_cents=8_000)
    assert claim_cap_cents(world.s, c) == 4_000


def test_nothing_happens_without_a_mandate(world):
    who, why = mandates.claim_check(world.s, _claim(world))
    assert who is None and "aren't in the mandate" in why


def test_a_small_confident_claim_is_paid_and_credited_to_the_admin(world):
    _mandate(world)
    who, why = mandates.claim_check(world.s, _claim(world))
    assert why is None and who.id == world.maya.id


@pytest.mark.parametrize("kw, expected", [
    ({"verdict": "reject"}, "The AI said reject"),
    ({"verdict": "needs_more_info"}, "The AI said needs more info"),
    ({"confidence": 0.70}, "70% sure, under 85%"),
    ({"reason": "Looks fine | Red flags: evidence link is broken"}, "red flags"),
    ({"invoice_cents": 20_000}, "over the $50.00 limit"),       # pays $100, limit $50
])
def test_a_claim_outside_the_mandate_waits_for_a_person(world, kw, expected):
    _mandate(world)
    who, why = mandates.claim_check(world.s, _claim(world, **kw))
    assert who is None and expected in why


def test_a_claim_may_not_drain_the_pool(world):
    _mandate(world)
    world.guild.pool_balance = 5_000            # paying $40 would leave $10, under a quarter
    who, why = mandates.claim_check(world.s, _claim(world))
    assert who is None and "quarter of the pool" in why


def test_at_most_three_automatic_claims_a_week(world):
    m = _mandate(world)
    for _ in range(mandates.WEEKLY_LIMIT):
        world.s.add(AgentAction(guild_id=world.guild.id, action="mandate.applied",
                                inputs={"kind": "claim", "mandate_id": str(m.id)}))
    world.s.flush()
    who, why = mandates.claim_check(world.s, _claim(world))
    assert who is None and "3 claims this week" in why


def test_the_admin_who_set_it_cannot_approve_their_own_claim(world):
    _mandate(world)
    c = _claim(world)
    c.member_id = world.maya.id
    who, why = mandates.claim_check(world.s, c)
    assert who is None and "another admin decides" in why


def test_mandate_stops_if_its_admin_loses_admin(world):
    _mandate(world)
    world.maya.role = "member"
    who, why = mandates.claim_check(world.s, _claim(world))
    assert who is None and "isn't an admin" in why


def test_platform_kill_switch_pauses_everything(world):
    _mandate(world, remind_max_tier=2)
    assert mandates.remind_tier(world.s, world.guild.id) == 2
    world.s.add(PlatformSetting(key="ai_enabled", value={"on": False}, updated_by_email="ops@x.test"))
    world.s.flush()
    platform_settings.clear_cache()
    who, why = mandates.claim_check(world.s, _claim(world))
    assert who is None and "AI is turned off" in why
    assert mandates.remind_tier(world.s, world.guild.id) == 0


def _advance(world, cents):
    _, inv = world.invoice(50_000)
    adv = Advance(guild_id=world.guild.id, invoice_id=inv.id, member_id=world.sara.id,
                  advance_cents=cents, fee_cents=cents * 2 // 100, status="pending")
    world.s.add(adv)
    world.s.flush()
    return adv


def test_small_advance_is_inside_the_mandate(world):
    _mandate(world)
    who, why = mandates.advance_check(world.s, _advance(world, 4_000))
    assert why is None and who.id == world.maya.id


def test_large_advance_waits_for_a_person(world):
    _mandate(world)
    who, why = mandates.advance_check(world.s, _advance(world, 35_000))
    assert who is None and "over the $50.00 limit" in why
