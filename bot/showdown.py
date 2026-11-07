"""Learn the opponent's real ranges from the hands they show down.

At a showdown we see their five cards, so for each line they took we can
measure how strong their hand actually was:

  * preflop raises / calls of our raise -> their preflop percentile
  * postflop bets and raises            -> their made-hand strength on that
                                            street's board, as a percentile
                                            against random hands

The 20th percentile of those samples estimates the bottom of the range
they take that line with. Estimates are blended with the strategy's prior
by sample count, so a few showdowns only nudge it. (Showdown hands skew
strong because bluffs often fold first; the blend keeps that in check.)
"""

from __future__ import annotations

import numpy as np

from bot import fasteval as fe
from bot import preflop
from game import Action, Street

RAISES = (Action.RAISE_HALF, Action.RAISE_POT)
BOARD_SIZE = {Street.FLOP: 3, Street.TURN: 4, Street.RIVER: 5}


class ShowdownLearner:
    def __init__(self, seed: int = 0, ref_samples: int = 400) -> None:
        self.rng = np.random.default_rng(seed)
        self.ref_samples = ref_samples
        self.raise_pcts: list[float] = []
        self.call_pcts: list[float] = []
        self.bet_strengths: list[float] = []
        self.raise_strengths: list[float] = []

    def strength_percentile(self, hole, board) -> float:
        """Made-hand strength of `hole` on `board` vs random hands."""
        triples = fe.board_triples_partial(board)
        mine = int(fe.RANK[fe.hole_pairs(np.asarray(hole))[:, None], triples[None, :]].max())
        dead = np.asarray(list(hole) + list(board))
        live = np.setdiff1d(np.arange(36), dead)
        keys = self.rng.random((self.ref_samples, live.size))
        others = live[np.argpartition(keys, 4, axis=1)[:, :5]]
        theirs = fe.RANK[fe.hole_pairs(others)[:, :, None], triples[None, None, :]].max(axis=(1, 2))
        return float(((theirs < mine) + 0.5 * (theirs == mine)).mean())

    def add(self, opp_hole, board, opp_steps, we_raised_preflop: bool) -> None:
        pre = [s for s in opp_steps if s.street == Street.PREFLOP]
        pct = preflop.percentile(opp_hole)
        if any(s.action in RAISES for s in pre):
            self.raise_pcts.append(pct)
        elif we_raised_preflop and pre:
            self.call_pcts.append(pct)
        for street, size in BOARD_SIZE.items():
            acts = [s for s in opp_steps if s.street == street and s.action in RAISES]
            if not acts:
                continue
            strength = self.strength_percentile(opp_hole, board[:size])
            (self.raise_strengths if len(acts) >= 2 else self.bet_strengths).append(strength)

    @staticmethod
    def _blend(samples: list[float], prior: float, prior_weight: float = 8.0, q: float = 0.2) -> float:
        if not samples:
            return prior
        est = float(np.quantile(samples, q))
        n = len(samples)
        return (est * n + prior * prior_weight) / (n + prior_weight)

    def raise_floor(self, prior: float) -> float:
        return self._blend(self.raise_pcts, prior)

    def call_floor(self, prior: float) -> float:
        return self._blend(self.call_pcts, prior)

    def bet_level(self, prior: float) -> float:
        return self._blend(self.bet_strengths, prior)

    def raise_level(self, prior: float) -> float:
        return self._blend(self.raise_strengths, prior)
