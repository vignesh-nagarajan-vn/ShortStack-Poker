"""The numpy evaluator must order hands exactly like evaluator.omaha_score."""

import random

import numpy as np

from bot import fasteval as fe
from evaluator import cards_from_str, omaha_score


def test_rank_matches_omaha_score_on_random_deals():
    rng = random.Random(5)
    for _ in range(3000):
        cards = rng.sample(range(36), 10)
        hole, board = cards[:5], cards[5:]
        assert fe.score_of_rank(fe.best_rank(hole, board)) == omaha_score(hole, board)


def test_batch_matches_single():
    rng = np.random.default_rng(3)
    deals = np.array([rng.permutation(36)[:10] for _ in range(500)])
    ranks = fe.best_rank_batch(fe.hole_pairs(deals[:, :5]), fe.board_triples(deals[:, 5:]))
    for d, r in zip(deals, ranks):
        assert r == fe.best_rank(d[:5].tolist(), d[5:].tolist())


def test_two_plus_three_rule():
    # From the guide: four hearts on board and one heart in hand is NOT a flush.
    board = cards_from_str("Ah Kh Qh Jh 6c")
    hole = cards_from_str("Th 7s 7d 8c 9c")
    score = fe.score_of_rank(fe.best_rank(hole, board))
    assert score == omaha_score(hole, board)
    assert score >> 20 == 3  # king-high straight


def test_overlapping_cards_rank_zero():
    p = fe.PAIR_INDEX[0, 1]
    t = fe.TRIPLE_INDEX[1, 2, 3]
    assert fe.RANK[p, t] == 0


def test_shipped_table_matches_fresh_build():
    rank, by_colex, distinct = fe.build_rank_tables()
    assert np.array_equal(rank, fe.RANK)
    assert np.array_equal(by_colex, fe.RANK_BY_COLEX)
    assert np.array_equal(distinct, fe.DISTINCT_SCORES)
