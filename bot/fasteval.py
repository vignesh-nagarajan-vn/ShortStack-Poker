"""Vectorized Omaha scoring with numpy.

evaluator.omaha_score does 100 dict lookups per call (~75 us in CPython),
which is far too slow to simulate inside an 8 s time bank. Instead we
build one table at startup:

    RANK[pair, triple] = strength of (2 hole cards + 3 board cards)

for all 630 two-card pairs and 7140 three-card triples (a 9 MB uint16
array). Building it takes ~2 s, so tools/build_tables.py saves it to
data/fasteval_tables.npz and startup just loads it (rebuilding only if
the file is missing or damaged). "Strength" is the dense rank of evaluator's score, so comparing
ranks is exactly comparing omaha_score values. A full Omaha hand is then
max over a 10 x 10 block, and thousands of hands are scored per numpy call.
"""

from __future__ import annotations

import os
from itertools import combinations
from math import comb

import numpy as np

from evaluator import NUM_CARDS, get_table

# Positions of the 10 ways to take 2 of 5 and 3 of 5 cards.
PAIR_POS = np.array(list(combinations(range(5), 2)), dtype=np.intp)     # (10, 2)
TRIPLE_POS = np.array(list(combinations(range(5), 3)), dtype=np.intp)   # (10, 3)

_PAIRS = list(combinations(range(NUM_CARDS), 2))       # 630
_TRIPLES = list(combinations(range(NUM_CARDS), 3))     # 7140

# BINOM[n, k] = C(n, k); used for colex indexes of sorted card tuples.
BINOM = np.array([[comb(n, k) for k in range(6)] for n in range(NUM_CARDS + 1)], dtype=np.int64)


def colex_index(sorted_cards: np.ndarray) -> np.ndarray:
    """Colex rank of ascending card tuples along the last axis (k = 1..5 cards)."""
    k = sorted_cards.shape[-1]
    out = np.zeros(sorted_cards.shape[:-1], dtype=np.int64)
    for i in range(k):
        out += BINOM[sorted_cards[..., i], i + 1]
    return out


TABLE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "data", "fasteval_tables.npz")


def _index_tables():
    """pair/triple card lookups (cheap, always built in-process)."""
    pair_index = np.full((NUM_CARDS, NUM_CARDS), -1, dtype=np.int16)
    for i, (a, b) in enumerate(_PAIRS):
        pair_index[a, b] = pair_index[b, a] = i
    triple_index = np.full((NUM_CARDS,) * 3, -1, dtype=np.int16)
    for i, (a, b, c) in enumerate(_TRIPLES):
        for x, y, z in ((a, b, c), (a, c, b), (b, a, c), (b, c, a), (c, a, b), (c, b, a)):
            triple_index[x, y, z] = i
    return pair_index, triple_index


def build_rank_tables():
    """Compute (RANK, RANK_BY_COLEX, DISTINCT_SCORES) from evaluator's table."""
    # Score of every 5-card hand, indexed by colex rank, as a dense rank.
    table = get_table()
    five = np.array(list(combinations(range(NUM_CARDS), 5)), dtype=np.int64)    # colex order
    masks = (np.left_shift(1, five)).sum(axis=1)
    scores = np.fromiter((table[int(m)] for m in masks), dtype=np.int64, count=len(masks))
    distinct = np.unique(scores)                       # ascending
    score5_rank = (np.searchsorted(distinct, scores) + 1).astype(np.uint16)   # 0 = invalid
    order = colex_index(five)
    rank_by_colex = np.zeros(comb(NUM_CARDS, 5), dtype=np.uint16)
    rank_by_colex[order] = score5_rank

    pairs = np.array(_PAIRS, dtype=np.int64)          # (630, 2)
    triples = np.array(_TRIPLES, dtype=np.int64)      # (7140, 3)
    cards = np.concatenate([
        np.broadcast_to(pairs[:, None, :], (len(pairs), len(triples), 2)),
        np.broadcast_to(triples[None, :, :], (len(pairs), len(triples), 3)),
    ], axis=2).reshape(-1, 5)
    cards.sort(axis=1)
    valid = np.all(cards[:, 1:] != cards[:, :-1], axis=1)
    rank = np.zeros(len(cards), dtype=np.uint16)
    rank[valid] = rank_by_colex[colex_index(cards[valid])]
    return rank.reshape(len(pairs), len(triples)), rank_by_colex, distinct


def _load_or_build():
    try:
        with np.load(TABLE_PATH) as data:
            rank, by_colex, distinct = data["rank"], data["rank_by_colex"], data["distinct"]
        if rank.shape == (len(_PAIRS), len(_TRIPLES)) and by_colex.shape == (comb(NUM_CARDS, 5),):
            return rank, by_colex, distinct
    except (OSError, KeyError, ValueError):
        pass
    return build_rank_tables()


PAIR_INDEX, TRIPLE_INDEX = _index_tables()
RANK, RANK_BY_COLEX, DISTINCT_SCORES = _load_or_build()


def hole_pairs(holes: np.ndarray) -> np.ndarray:
    """(..., 5) hole cards -> (..., 10) pair indexes."""
    return PAIR_INDEX[holes[..., PAIR_POS[:, 0]], holes[..., PAIR_POS[:, 1]]]


def board_triples(boards: np.ndarray) -> np.ndarray:
    """(..., 5) board cards -> (..., 10) triple indexes."""
    return TRIPLE_INDEX[boards[..., TRIPLE_POS[:, 0]], boards[..., TRIPLE_POS[:, 1]],
                        boards[..., TRIPLE_POS[:, 2]]]


def best_rank_batch(pairs: np.ndarray, triples: np.ndarray) -> np.ndarray:
    """(N, 10) pairs and (N, 10) triples -> (N,) best hand rank (Omaha 2 + 3)."""
    return RANK[pairs[:, :, None], triples[:, None, :]].max(axis=(1, 2))


def best_rank(hole, board) -> int:
    """Rank of one Omaha hand; orders hands exactly like omaha_score."""
    p = hole_pairs(np.asarray(hole, dtype=np.intp))
    t = board_triples(np.asarray(board, dtype=np.intp))
    return int(RANK[p[:, None], t[None, :]].max())


def score_of_rank(rank: int) -> int:
    """The evaluator score for a dense rank (for category_of / debugging)."""
    return int(DISTINCT_SCORES[rank - 1])
