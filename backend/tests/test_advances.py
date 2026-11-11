"""12B Paid on day one: the money math and paying the pool back. The AI never touches any of this."""
import itertools

import pytest
from sqlmodel import select

from app.models import Advance, PoolTx
from app.services import advances
from app.services.advances import FEE_PCT, MAX_ADVANCE_CENTS, amounts


def _amounts(world, invoice_cents, referrer=None):
    job, _ = world.invoice(invoice_cents, referrer=referrer)
    return amounts(world.guild, job, invoice_cents)


def test_advance_is_70_percent_of_a_small_invoice(world):
    a = _amounts(world, 50_000)                      # $500, no referrer: worker share is 95%
    assert a["worker_share_cents"] == 47_500
    assert a["advance_cents"] == 35_000              # 70% of the invoice
    assert a["fee_cents"] == 700                     # 2% of the advance
    assert a["later_cents"] == 47_500 - 35_700       # rest of the share when the client pays


def test_advance_never_goes_over_1000_dollars(world):
    a = _amounts(world, 500_000)                     # $5,000 invoice
    assert a["advance_cents"] == MAX_ADVANCE_CENTS == 100_000


def test_advance_and_fee_fit_inside_a_small_worker_share(world):
    world.guild.worker_pct, world.guild.referrer_pct, world.guild.pool_pct = 60, 35, 5
    a = _amounts(world, 10_000, referrer=world.maya)  # worker keeps only 60%, less than 70% / 1.02
    assert a["worker_share_cents"] == 6_000
    assert a["advance_cents"] == 6_000 * 100 // (100 + FEE_PCT)
    assert a["repay_cents"] <= a["worker_share_cents"]


@pytest.mark.parametrize("pcts", [(85, 10, 5), (60, 35, 5), (70, 20, 10), (90, 5, 5)])
def test_the_pool_is_always_paid_back_in_full(world, pcts):
    """For any invoice and any split, advance + fee fits in the worker's share, so the pool never loses money."""
    world.guild.worker_pct, world.guild.referrer_pct, world.guild.pool_pct = pcts
    for cents, has_ref in itertools.product([1, 99, 1_000, 33_333, 142_857, 1_000_000], [True, False]):
        job, _ = world.invoice(cents, referrer=world.maya if has_ref else None)
        a = amounts(world.guild, job, cents)
        assert 0 <= a["advance_cents"] <= MAX_ADVANCE_CENTS
        assert a["repay_cents"] == a["advance_cents"] + a["fee_cents"]
        assert a["repay_cents"] <= a["worker_share_cents"], (cents, pcts, has_ref)
        assert a["later_cents"] >= 0


def _paid_advance(world, invoice_cents=50_000):
    job, inv = world.invoice(invoice_cents)
    a = amounts(world.guild, job, invoice_cents)
    adv = Advance(guild_id=world.guild.id, invoice_id=inv.id, member_id=world.sara.id,
                  advance_cents=a["advance_cents"], fee_cents=a["fee_cents"], status="paid")
    world.s.add(adv)
    world.s.flush()
    return job, inv, adv, a


def test_client_payment_repays_the_pool_first(world):
    job, inv, adv, a = _paid_advance(world)
    pool_before = world.guild.pool_balance
    taken = advances.take_back(world.s, world.guild, inv, job, a["worker_share_cents"])

    assert taken == a["repay_cents"]
    assert world.guild.pool_balance == pool_before + a["repay_cents"]
    assert adv.status == "repaid"
    txs = {t.source: t.amount for t in world.s.exec(select(PoolTx)).all()}
    assert txs == {"advance_repaid": a["advance_cents"], "advance_fee": a["fee_cents"]}


def test_a_pending_request_is_declined_when_the_client_pays_first(world):
    job, inv = world.invoice(50_000)
    pending = Advance(guild_id=world.guild.id, invoice_id=inv.id, member_id=world.sara.id,
                      advance_cents=35_000, fee_cents=700, status="pending")
    world.s.add(pending)
    world.s.flush()
    assert advances.take_back(world.s, world.guild, inv, job, 47_500) == 0
    assert pending.status == "declined"


def test_an_open_advance_blocks_a_claim_on_the_same_invoice(world):
    _, inv, adv, _ = _paid_advance(world)
    assert advances.blocks_claim(world.s, inv.id)
    adv.status = "repaid"
    world.s.add(adv)
    world.s.flush()
    assert not advances.blocks_claim(world.s, inv.id)
