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
