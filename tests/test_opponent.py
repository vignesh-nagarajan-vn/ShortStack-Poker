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
    assert m.rate("fold_to_bet") > 0.7   # few postflop samples: still near the prior


def test_maniac_is_read_as_aggressive():
    m = _model_after_half(Maniac)
    assert m.rate("pfr") > 0.5
    assert m.rate("aggression") > 0.5
    assert m.rate("fold_to_bet") < 0.1


def test_showdown_learning_reads_a_tight_raiser():
    from bot.showdown import ShowdownLearner
    from bot.opponent import Step
    from game import Action, Street
    from evaluator import cards_from_str as c
    learner = ShowdownLearner(seed=1)
    strong = c("Ah Ad Kh Kd Qs")
    for _ in range(30):
        learner.add(strong, c("As Kc 6d 7h 8s"), [Step(Street.PREFLOP, False, Action.RAISE_POT),
                                                   Step(Street.FLOP, False, Action.RAISE_HALF)], False)
    assert learner.raise_floor(0.45) > 0.8      # they only raise premium hands
    assert learner.bet_level(0.40) > 0.7        # and only bet the flop with strong made hands


def test_strength_percentile_orders_hands():
    from bot.showdown import ShowdownLearner
    from evaluator import cards_from_str as c
    learner = ShowdownLearner(seed=2)
    board = c("As Kc 6d")
    assert learner.strength_percentile(c("Ah Ad Kh 7c 8c"), board) > 0.9
    assert learner.strength_percentile(c("7c 8d 9h Th Qs"), board) < 0.5
