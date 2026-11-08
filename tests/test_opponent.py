"""The opponent model rebuilds hands correctly and learns sensible rates."""

from sim.opponents import CheckFold, Maniac
from sim.players import BrainPlayer
from sim.run_match import play_half
from sim.players import class_factory


def _brain_after_half(opponent_cls, deals=300):
    holder = {}

    def make_us(config):
        p = BrainPlayer(config)
        holder["p"] = p
        return p

    play_half(make_us, class_factory(opponent_cls, "opp"), "model", 1, deals)
    return holder["p"].brain


def _model_after_half(opponent_cls, deals=300):
    return _brain_after_half(opponent_cls, deals).opponent


def test_check_folder_is_read_as_passive_and_put_on_autopilot():
    brain = _brain_after_half(CheckFold)
    m = brain.opponent
    assert m.hands == 300
    assert m.rate("pfr") < 0.05
    assert m.rate("vpip") < 0.05
    # It folds to every bet, so we steal every hand and it never sees a flop.
    assert brain.autopilot.active


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


def test_river_called_wins_counts_only_called_river_bets():
    from game import Action, HandResult, Street
    from bot.opponent import OpponentModel, Step

    def hand(steps, winner):
        m.observe_hand(steps, HandResult(hand_index=0, my_net=0, pot=40, went_to_showdown=True,
                                         board=(), opp_hole=None, winner=winner))

    m = OpponentModel()
    pre = [Step(Street.PREFLOP, False, Action.CHECK_CALL), Step(Street.PREFLOP, True, Action.CHECK_CALL)]
    bet_called = [Step(Street.RIVER, False, Action.CHECK_CALL), Step(Street.RIVER, True, Action.RAISE_POT),
                  Step(Street.RIVER, False, Action.CHECK_CALL)]
    we_called = [Step(Street.RIVER, False, Action.RAISE_HALF), Step(Street.RIVER, True, Action.CHECK_CALL)]
    hand(pre + bet_called, "me")
    hand(pre + bet_called, "opp")
    hand(pre + we_called, "me")          # they bet, we called: not counted
    r = m.river_called_wins
    assert r.total == 2 and r.hits == 1


def test_thin_river_shift_scales_with_called_bet_win_rate():
    from bot.core import Brain
    from game import AgentConfig

    brain = Brain(AgentConfig())
    r = brain.opponent.river_called_wins
    assert brain.strategy.thin_river_shift() == 0.0      # no evidence yet
    for _ in range(40):
        r.add(True)                                      # every called bet won
    assert abs(brain.strategy.thin_river_shift() - brain.params["thin_river_shift"]) < 1e-9
    r2 = type(r)(0.65)
    for i in range(40):
        r2.add(i % 2 == 0)                               # coin flip: no shift
    brain.opponent.river_called_wins = r2
    assert brain.strategy.thin_river_shift() == 0.0
