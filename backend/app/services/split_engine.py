from dataclasses import dataclass


@dataclass(frozen=True)
class Split:
    worker_cents: int
    referrer_cents: int
    pool_cents: int
    total_cents: int


def split_payment(
    amount_cents: int,
    has_referrer: bool,
    worker_pct: int = 85,
    referrer_pct: int = 10,
    pool_pct: int = 5,
) -> Split:
    """Split a payment into worker, referrer, and pool shares.

    Integer cents only. Rounding leftovers go to the worker,
    so the three shares always add up to the original amount.
    """
    if amount_cents < 0:
        raise ValueError("amount_cents must be non-negative")
    for pct in (worker_pct, referrer_pct, pool_pct):
        if not 0 <= pct <= 100:
            raise ValueError("each percentage must be between 0 and 100")
    if worker_pct + referrer_pct + pool_pct != 100:
        raise ValueError("percentages must sum to 100")

    if not has_referrer:
        worker_pct = 100 - pool_pct
        referrer_pct = 0

    worker = amount_cents * worker_pct // 100
    referrer = amount_cents * referrer_pct // 100
    pool = amount_cents * pool_pct // 100

    worker += amount_cents - (worker + referrer + pool)

    return Split(
        worker_cents=worker,
        referrer_cents=referrer,
        pool_cents=pool,
        total_cents=amount_cents,
    )