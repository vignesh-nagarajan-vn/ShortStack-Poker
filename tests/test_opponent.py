"""The opponent model rebuilds hands correctly and learns sensible rates."""

from sim.opponents import CheckFold, Maniac
from sim.players import BrainPlayer
from sim.run_match import play_half
from sim.players import class_factory


def _model_after_half(opponent_cls, deals=300):
    holder = {}

    def make_us(config):
        p = BrainPlayer(config)
        holder["p"] = p
        return p

    play_half(make_us, class_factory(opponent_cls, "opp"), "model", 1, deals)
    return holder["p"].brain.opponent


def test_check_folder_is_read_as_passive_and_folding():
    m = _model_after_half(CheckFold)
    assert m.hands == 300
    assert m.rate("pfr") < 0.05
    assert m.rate("aggression") < 0.1
    assert m.rate("fold_to_bet") > 0.8


def test_maniac_is_read_as_aggressive():
    m = _model_after_half(Maniac)
    assert m.rate("pfr") > 0.5
    assert m.rate("aggression") > 0.5
    assert m.rate("fold_to_bet") < 0.1
