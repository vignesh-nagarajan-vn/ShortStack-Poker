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
        self.bet_by_street: dict[Street, list[float]] = {st: [] for st in BOARD_SIZE}
        self.raise_strengths: list[float] = []
        self.river_call_strengths: list[float] = []   # hands that called our river bets
        # Single postflop bets by size, to learn whether size tells strength.
        self.bet_by_size: dict[Action, list[float]] = {Action.RAISE_HALF: [], Action.RAISE_POT: []}

    def strength_percentile(self, hole, board) -> float:
        """Made-hand strength of `hole` on `board` vs random hands."""
        triples = fe.board_triples_partial(board)
        by_pair = fe.pair_best(triples)
        mine = int(by_pair[fe.hole_pairs(np.asarray(hole))].max())
        dead = np.asarray(list(hole) + list(board))
        live = np.setdiff1d(np.arange(36), dead)
        keys = self.rng.random((self.ref_samples, live.size))
        others = live[np.argpartition(keys, 4, axis=1)[:, :5]]
        theirs = by_pair[fe.hole_pairs(others)].max(axis=1)
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
            if len(acts) >= 2:
                self.raise_strengths.append(strength)
            else:
                self.bet_strengths.append(strength)
                self.bet_by_street[street].append(strength)
                self.bet_by_size[acts[0].action].append(strength)

    def add_river_call(self, opp_hole, board) -> None:
        """They called our river bet and showed this hand."""
        self.river_call_strengths.append(self.strength_percentile(opp_hole, board))

    def river_call_floor(self, prior: float = 0.5, q: float = 0.2) -> float:
        """Made-hand strength at the bottom of their river calling range."""
        return self._blend(self.river_call_strengths, prior, q=q)

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

    def bet_level(self, prior: float, street: Street | None = None) -> float:
        """Bottom of their single-bet range. With `street`, that street's
        showdowns refine the all-streets estimate: a bot can semi-bluff the
        flop and turn wide and still bet the river only for value."""
        level = self._blend(self.bet_strengths, prior)
        if street is None:
            return level
        return self._blend(self.bet_by_street[street], level)

    def size_tell(self, prior: float, prior_weight: float = 6.0) -> float:
        """How much their bet size tracks strength, 0 (not at all) to 1: the
        gap between the made strength they show after pot bets and after
        half-pot bets, 0.2 of a percentile gap counting as a full tell.
        Blended with `prior` by the smaller sample."""
        half, pot = self.bet_by_size[Action.RAISE_HALF], self.bet_by_size[Action.RAISE_POT]
        n = min(len(half), len(pot))
        if n == 0:
            return prior
        gap = float(np.mean(pot)) - float(np.mean(half))
        raw = min(1.0, max(0.0, gap / 0.2))
        return (raw * n + prior * prior_weight) / (n + prior_weight)

    def raise_level(self, prior: float) -> float:
        return self._blend(self.raise_strengths, prior)
