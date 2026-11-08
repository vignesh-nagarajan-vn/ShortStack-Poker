"""Monte Carlo equity on top of the numpy evaluator.

One call deals `n` opponent hands and board runouts at once and scores
them with a handful of numpy gathers, so ~500 samples cost well under a
millisecond. Our own pair indexes are computed once per call, and on the
river our score is a single number.

An optional weight function turns plain "equity vs a random hand" into
equity vs a *range*: each sampled opponent hand gets a weight (e.g. how
likely that hand is to have taken the observed betting line), and the
result is the weighted win rate.
"""

from __future__ import annotations

from typing import Callable, Optional, Sequence

import numpy as np

from bot import fasteval as fe
from evaluator import NUM_CARDS

SHUFFLE_MIN_N = 64     # below this, sorting random keys is cheaper than swapping

WeightFn = Callable[[np.ndarray], np.ndarray]   # (n, 5) opponent holes -> (n,) weights


class EquityEngine:
    """Owns the random generator so a half is reproducible from its seed."""

    def __init__(self, seed: int = 0) -> None:
        self.rng = np.random.default_rng(seed)

    def sample(self, dead: Sequence[int], n: int, k: int) -> np.ndarray:
        """n rows of k distinct cards drawn from the cards not in `dead`.

        A partial Fisher-Yates shuffle run on all rows at once: k column
        swaps instead of sorting n x 31 random keys (about 2x faster)."""
        mask = np.ones(NUM_CARDS, dtype=bool)
        mask[np.asarray(dead, dtype=np.intp)] = False
        live = np.flatnonzero(mask)
        if n < SHUFFLE_MIN_N:              # the shuffle's per-swap overhead dominates
            idx = np.argpartition(self.rng.random((n, live.size)), k - 1, axis=1)[:, :k]
            return live[idx]
        live = live.astype(np.int8)
        size = live.size
        deck = np.broadcast_to(live, (n, size)).copy()
        rows = np.arange(n)
        r = self.rng.random((n, k))
        for i in range(k):
            j = i + (r[:, i] * (size - i)).astype(np.intp)
            np.minimum(j, size - 1, out=j)          # r * m can round up to m
            picked = deck[rows, j]
            deck[rows, j] = deck[:, i]
            deck[:, i] = picked
        return deck[:, :k].astype(np.intp)

    def equity(self, hole: Sequence[int], board: Sequence[int], n: int,
               weight_fn: Optional[WeightFn] = None) -> float:
        """Probability of winning at showdown (ties count half) against an
        opponent hand drawn at random, or weighted by weight_fn."""
        n = max(1, int(n))
        hole = np.asarray(hole, dtype=np.intp)
        board = np.asarray(board, dtype=np.intp)
        need = 5 - board.size
        draw = self.sample(np.concatenate([hole, board]), n, 5 + need)
        opp = draw[:, :5]
        mine_by_triple = fe.triple_best(fe.hole_pairs(hole))   # (7140,), cached per hand
        opp_pairs = fe.hole_pairs(opp)                         # (n, 10)
        if need == 0:
            triples = fe.board_triples(board)                  # (10,)
            mine = int(mine_by_triple[triples].max())
            theirs = fe.pair_best(triples)[opp_pairs].max(axis=1)
        else:
            boards = np.concatenate([np.broadcast_to(board, (n, board.size)), draw[:, 5:]], axis=1)
            triples = fe.board_triples(boards)                 # (n, 10)
            mine = mine_by_triple[triples].max(axis=1)
            theirs = fe.best_rank_batch(opp_pairs, triples)
        result = (mine > theirs).astype(np.float64) + 0.5 * (mine == theirs)
        if weight_fn is None:
            return float(result.mean())
        w = np.asarray(weight_fn(opp), dtype=np.float64)
        total = w.sum()
        if not np.isfinite(total) or total <= 1e-9:
            return float(result.mean())
        return float((result * w).sum() / total)
