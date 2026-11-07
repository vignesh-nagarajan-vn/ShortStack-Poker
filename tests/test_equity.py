"""Monte Carlo equity: agrees with a brute-force reference and stays fast."""

import random
import time

import numpy as np

from bot.equity import EquityEngine
from evaluator import cards_from_str, omaha_score


def reference_equity(hole, board, sims, seed=0):
    rng = random.Random(seed)
    deck = [c for c in range(36) if c not in set(hole) | set(board)]
    need = 5 - len(board)
    total = 0.0
    for _ in range(sims):
        draw = rng.sample(deck, 5 + need)
        full = list(board) + draw[5:]
        a, b = omaha_score(hole, full), omaha_score(draw[:5], full)
        total += 1.0 if a > b else 0.5 if a == b else 0.0
    return total / sims


def test_matches_reference_on_each_street():
    eng = EquityEngine(1)
    rng = random.Random(2)
    for board_len in (0, 3, 4, 5):
        cards = rng.sample(range(36), 5 + board_len)
        hole, board = cards[:5], cards[5:]
        fast = eng.equity(hole, board, 20000)
        slow = reference_equity(hole, board, 4000)
        assert abs(fast - slow) < 0.03, (board_len, fast, slow)


def test_nuts_on_river_wins():
    eng = EquityEngine(0)
    board = cards_from_str("Ah Kh Qh 7c 6d")
    hole = cards_from_str("Jh Th 8s 8d 9c")      # royal flush with Jh Th
    assert eng.equity(hole, board, 2000) == 1.0


def test_average_equity_vs_random_is_half():
    eng = EquityEngine(4)
    rng = random.Random(9)
    vals = [eng.equity(rng.sample(range(36), 5), [], 400) for _ in range(300)]
    assert abs(np.mean(vals) - 0.5) < 0.02


def test_weights_shift_equity():
    eng = EquityEngine(3)
    hole = cards_from_str("6c 7d 8h 9s Js")
    plain = eng.equity(hole, [], 8000)
    # Opponent only holds hands containing an ace: our weak hand does worse.
    weighted = eng.equity(hole, [], 8000, weight_fn=lambda opp: (opp >> 2 == 8).any(axis=1))
    assert weighted < plain


def test_fast_enough():
    eng = EquityEngine(0)
    hole, board = cards_from_str("6c 7d 8h 9s Js"), cards_from_str("Ah Kd 6s")
    eng.equity(hole, board, 300)
    start = time.perf_counter()
    for _ in range(50):
        eng.equity(hole, board, 300)
    per_call = (time.perf_counter() - start) / 50
    assert per_call < 0.004, f"{per_call * 1e3:.2f} ms per 300-sample equity call"
