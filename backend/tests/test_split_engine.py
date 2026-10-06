import pytest

from app.services.split_engine import split_payment


def test_full_split_with_referrer():
    s = split_payment(10000, has_referrer=True)
    assert (s.worker_cents, s.referrer_cents, s.pool_cents) == (8500, 1000, 500)


def test_full_split_no_referrer():
    s = split_payment(10000, has_referrer=False)
    assert (s.worker_cents, s.referrer_cents, s.pool_cents) == (9500, 0, 500)


def test_remainder_goes_to_worker():
    s = split_payment(3333, has_referrer=True)
    assert (s.worker_cents, s.referrer_cents, s.pool_cents) == (2834, 333, 166)


def test_one_cent():
    s = split_payment(1, has_referrer=True)
    assert (s.worker_cents, s.referrer_cents, s.pool_cents) == (1, 0, 0)


def test_zero():
    s = split_payment(0, has_referrer=True)
    assert (s.worker_cents, s.referrer_cents, s.pool_cents) == (0, 0, 0)


def test_negative_rejected():
    with pytest.raises(ValueError):
        split_payment(-1, has_referrer=True)


def test_bad_percentages_rejected():
    with pytest.raises(ValueError):
        split_payment(1000, has_referrer=True, worker_pct=80, referrer_pct=10, pool_pct=5)


def test_custom_percentages():
    s = split_payment(10000, has_referrer=True, worker_pct=70, referrer_pct=20, pool_pct=10)
    assert (s.worker_cents, s.referrer_cents, s.pool_cents) == (7000, 2000, 1000)


@pytest.mark.parametrize("amount", [1, 7, 99, 100, 101, 999, 1000, 12345])
def test_sum_always_matches(amount):
    for has_ref in (True, False):
        s = split_payment(amount, has_referrer=has_ref)
        assert s.worker_cents + s.referrer_cents + s.pool_cents == amount