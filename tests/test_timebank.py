"""The time bank manager spreads time evenly and backs off when it runs low."""

from bot.timebank import HARD_CAP_SECONDS, MAX_SAMPLES, TimeBank


def test_fresh_bank_affords_samples():
    tb = TimeBank(8.0, 1000)
    n = tb.samples(0)
    assert 100 <= n <= MAX_SAMPLES


def test_allowance_never_exceeds_hard_cap():
    tb = TimeBank(8.0, 10)
    assert tb.allowance(9) <= HARD_CAP_SECONDS


def test_exhausted_bank_gives_zero_samples():
    tb = TimeBank(8.0, 1000)
    tb.spent = 5.0
    assert tb.samples(500) == 0


def test_cost_estimate_moves_toward_measurements():
    tb = TimeBank()
    for _ in range(50):
        tb.record_samples(100, 100 * 2e-5)
    assert abs(tb.cost_per_sample - 2e-5) < 1e-6
    assert tb.samples(0) < TimeBank().samples(0)
