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

WeightFn = Callable[[np.ndarray], np.ndarray]   # (n, 5) opponent holes -> (n,) weights


class EquityEngine:
    """Owns the random generator so a half is reproducible from its seed."""

    def __init__(self, seed: int = 0) -> None:
        self.rng = np.random.default_rng(seed)

    def sample(self, dead: Sequence[int], n: int, k: int) -> np.ndarray:
        """n rows of k distinct cards drawn from the cards not in `dead`."""
        live = np.setdiff1d(np.arange(NUM_CARDS), np.asarray(dead, dtype=np.intp), assume_unique=False)
        keys = self.rng.random((n, live.size))
        idx = np.argpartition(keys, k - 1, axis=1)[:, :k]
        return live[idx]

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
        my_pairs = fe.hole_pairs(hole)                         # (10,)
        opp_pairs = fe.hole_pairs(opp)                         # (n, 10)
        if need == 0:
            triples = fe.board_triples(board)                  # (10,)
            mine = int(fe.RANK[my_pairs[:, None], triples[None, :]].max())
            theirs = fe.RANK[opp_pairs[:, :, None], triples[None, None, :]].max(axis=(1, 2))
        else:
            boards = np.concatenate([np.broadcast_to(board, (n, board.size)), draw[:, 5:]], axis=1)
            triples = fe.board_triples(boards)                 # (n, 10)
            mine = fe.RANK[my_pairs[None, :, None], triples[:, None, :]].max(axis=(1, 2))
            theirs = fe.best_rank_batch(opp_pairs, triples)
        result = (mine > theirs).astype(np.float64) + 0.5 * (mine == theirs)
        if weight_fn is None:
            return float(result.mean())
        w = np.asarray(weight_fn(opp), dtype=np.float64)
        total = w.sum()
        if not np.isfinite(total) or total <= 1e-9:
            return float(result.mean())
        return float((result * w).sum() / total)
