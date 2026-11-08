"""Profile classification and hysteresis."""

from bot.opponent import OpponentModel
from bot.params import make
from bot.profile import Profiler, apply, classify


def _model(**rates):
    m = OpponentModel()
    for name, value in rates.items():
        r = m.rates[name]
        r.hits, r.total = value * 1000, 1000
    return m


def test_classify():
    assert classify(_model(aggression=0.8)) == "maniac"
    assert classify(_model(fold_to_bet=0.8)) == "nit"
    assert classify(_model(fold_to_bet=0.05)) == "station"
    assert classify(_model(aggression=0.1, fold_to_bet=0.4)) == "honest"


def test_apply_adds_and_sets():
    base = make()
    nit = apply(base, "nit")
    assert nit["sb_fold_below"] == 0.02
    assert abs(nit["sb_raise_half_above"] - (base["sb_raise_half_above"] - 0.25)) < 1e-9


def test_frequent_bettor_that_folds_is_not_a_maniac():
    # jish_4's shape: bets nearly every flop, folds to about half our bets.
    assert classify(_model(aggression=0.8, fold_to_bet=0.45), maniac_max_ftb=0.30) != "maniac"
    assert classify(_model(aggression=0.8, fold_to_bet=0.10), maniac_max_ftb=0.30) == "maniac"


def test_needs_two_evaluations_to_switch():
    prof = Profiler(make())
    m = _model(aggression=0.9, fold_to_bet=0.1)
    m.hands = 40
    assert not prof.update(m)
    m.hands = 60
    assert prof.update(m)
    assert prof.profile == "maniac"


def test_mode_switch_uses_recent_rates():
    from bot.profile import shifted
    m = _model(aggression=0.2, fold_to_bet=0.4)        # long-run: honest-ish
    for _ in range(60):
        m.rates["aggression"].add(True)                  # ...but now raising every time
    assert shifted(m)
    assert classify(m, recent=True) == "maniac"
