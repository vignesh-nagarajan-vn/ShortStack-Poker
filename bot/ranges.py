"""Weight functions that turn equity-vs-random into equity-vs-a-range.

A weight function receives the (n, 5) opponent hands the equity engine
sampled and returns how likely each one is to be in the opponent's range.
Weights are soft (never exactly 0) so a mis-read never makes a hand
impossible.
"""

from __future__ import annotations

import numpy as np

from bot import fasteval as fe
from bot import preflop

FLOOR_WEIGHT = 0.06


def preflop_floor(floor: float, softness: float = 0.06):
    """Opponent hands above percentile `floor` (soft edge)."""
    if floor <= 0.0:
        return None

    def weight(opp: np.ndarray) -> np.ndarray:
        pct = preflop.percentile_batch(opp)
        w = 1.0 / (1.0 + np.exp(-(pct - floor) / softness))
        return np.maximum(w, FLOOR_WEIGHT)

    return weight


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def made_strength(opp: np.ndarray, board) -> np.ndarray:
    """Each sampled hand's made-hand strength on the visible board, as its
    rank within the sample (0 = weakest sampled, 1 = strongest)."""
    triples = fe.board_triples_partial(board)
    pairs = fe.hole_pairs(opp)
    made = fe.RANK[pairs[:, :, None], triples[None, None, :]].max(axis=(1, 2))
    order = made.argsort(kind="stable").argsort(kind="stable")
    return order / max(1, len(opp) - 1)


def postflop_weight(board, pre_floor: float, aggression: float, softness: float = 0.12):
    """Opponent hands that fit both their preflop line (percentile floor)
    and their postflop aggression this hand (made-hand strength above the
    `aggression` share of the sample). 0 aggression = they only checked
    or called, so no strength filter."""
    board = list(board)

    def weight(opp: np.ndarray) -> np.ndarray:
        w = np.ones(len(opp))
        if pre_floor > 0:
            pct = preflop.percentile_batch(opp)
            w *= np.maximum(_sigmoid((pct - pre_floor) / 0.06), FLOOR_WEIGHT)
        if aggression > 0:
            strength = made_strength(opp, board)
            w *= np.maximum(_sigmoid((strength - aggression) / softness), FLOOR_WEIGHT)
        return w

    if pre_floor <= 0 and aggression <= 0:
        return None
    return weight
