"""Draw detection follows the exactly-2-plus-3 rule."""

import numpy as np

from bot.draws import flush_draw, has_draw, straight_window_count
from evaluator import cards_from_str as c


def test_flush_draw_needs_two_hole_cards_of_the_suit():
    board = c("Ah 9h 6c")
    two = np.array([c("Kh 7h 8c 8d Ts")])
    one = np.array([c("Kh 7s 8c 8d Ts")])
    assert flush_draw(two, board)[0] == 1.0
    assert flush_draw(one, board)[0] == 0.0


def test_straight_windows():
    assert straight_window_count(c("8c 9d Ks Kd As"), c("Tc Jh 6s")) >= 2
    assert straight_window_count(c("Qc Qd Qs 9d 9h"), c("6c 7h As")) == 0


def test_no_draws_on_the_river():
    assert not has_draw(c("Kh 7h 8c 8d Ts"), c("Ah 9h 6c 7d Qs"))


def test_allin_odds():
    from bot.context import Ctx
    from game import Game, Action, make_deal
    g = Game(make_deal("x", 0), 0)
    g.apply(Action.RAISE_POT)            # button to 6
    g.apply(Action.RAISE_POT)            # big blind to 18
    g.apply(Action.CHECK_CALL)           # pot 36, flop
    g.apply(Action.RAISE_POT)            # BB bets 36, all but 26 in
    ctx = Ctx(g.observation(g.to_act))   # button faces 36 with 62 behind
    # Calling 36 leaves 26: all 62 risked to win 36 + 36 + 26 + 26 = 124 total.
    assert abs(ctx.allin_odds - 62 / 160) < 1e-9
    assert ctx.committed_after_call(0.5)
