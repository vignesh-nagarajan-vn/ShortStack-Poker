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


def test_slow_probe_scales_overhead_and_cuts_thinking():
    from bot.timebank import OVERHEAD_PER_REQUEST, REF_PROBE_SECONDS
    fast, slow = TimeBank(8.0, 1000), TimeBank(8.0, 1000)
    fast.record_probe(REF_PROBE_SECONDS * 0.8)
    slow.record_probe(REF_PROBE_SECONDS * 3.0)
    assert fast.load_scale() == 1.0 and abs(fast.overhead() - OVERHEAD_PER_REQUEST) < 1e-12
    assert abs(slow.load_scale() - 3.0) < 1e-9
    for tb in (fast, slow):
        tb.spent, tb.requests, tb.decisions = 1.0, 1500, 1500
    assert slow.allowance(500) < fast.allowance(500)


def test_virtual_clock_brain_skips_the_probe():
    from bot.core import Brain
    from game import AgentConfig
    from sim.players import VirtualClock
    assert Brain(AgentConfig(), clock=VirtualClock()).timebank.probes == []
    assert len(Brain(AgentConfig()).timebank.probes) == 1
