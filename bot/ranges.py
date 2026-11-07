"""Weight functions that turn equity-vs-random into equity-vs-a-range.

A weight function receives the (n, 5) opponent hands the equity engine
sampled and returns how likely each one is to be in the opponent's range.
Weights are soft (never exactly 0) so a mis-read never makes a hand
impossible.
"""

from __future__ import annotations

import numpy as np

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
