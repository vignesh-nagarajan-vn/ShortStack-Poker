"""Preflop hand strength from the precomputed equity table.

data/preflop_equity.npz holds, for each of the 376,992 five-card hands
(by colex index), its equity against a random hand. At load time we also
turn it into a percentile: the share of all hands that are weaker, so 0.9
means "top 10% of starting hands". Both lookups are O(1) and vectorized.

If the file is ever missing, `available` is False and callers fall back to
Monte Carlo equity, so the bot still plays (just slower).
"""

from __future__ import annotations

import os

import numpy as np

from bot.fasteval import colex_index

TABLE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "data", "preflop_equity.npz")


def _load():
    try:
        with np.load(TABLE_PATH) as data:
            eq = data["equity"].astype(np.float32) / 65535.0
        if eq.shape != (376992,):
            raise ValueError("bad preflop table shape")
    except (OSError, KeyError, ValueError):
        return None, None
    order = np.argsort(eq, kind="stable")
    pct = np.empty_like(eq)
    pct[order] = np.arange(eq.size, dtype=np.float32) / (eq.size - 1)
    return eq, pct


EQUITY, PERCENTILE = _load()
available = EQUITY is not None


def _index(hole) -> int:
    cards = np.sort(np.asarray(hole, dtype=np.int64))
    return int(colex_index(cards))


def equity(hole) -> float:
    """Equity of a starting hand against one random hand."""
    return float(EQUITY[_index(hole)]) if available else 0.5


def percentile(hole) -> float:
    """Share of starting hands weaker than this one (0 = worst, 1 = best)."""
    return float(PERCENTILE[_index(hole)]) if available else 0.5


def percentile_batch(holes: np.ndarray) -> np.ndarray:
    """(n, 5) hands -> (n,) percentiles."""
    if not available:
        return np.full(len(holes), 0.5, dtype=np.float32)
    return PERCENTILE[colex_index(np.sort(holes, axis=1).astype(np.int64))]
