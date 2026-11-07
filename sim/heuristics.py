"""Deliberately "typical" helpers for the opponent pool.

These mimic what a competitor would write from the participant guide: a
feature-based preflop score and a naive Monte Carlo equity against one
random hand using omaha_score. They are NOT what our bot uses.
"""

from __future__ import annotations

import random
from collections import Counter

from evaluator import NUM_CARDS, omaha_score


def preflop_score(hole) -> float:
    """A hand-written 0..1 preflop strength from pairs, suits, connectivity and high cards."""
    ranks = [c >> 2 for c in hole]
    suits = Counter(c & 3 for c in hole)
    counts = Counter(ranks)
    score = sum(ranks) / (5 * 8) * 0.35                       # high cards
    pairs = [r for r, n in counts.items() if n >= 2]
    if pairs:
        score += 0.15 + 0.02 * max(pairs)                     # best pair
    if any(n >= 3 for n in counts.values()):
        score -= 0.08                                         # trips in hand are weak in Omaha
    suited = [s for s, n in suits.items() if n >= 2]
    score += 0.08 * min(len(suited), 2)                       # one or two flush draws
    if any(n >= 4 for n in suits.values()):
        score -= 0.05                                         # too many of one suit
    distinct = sorted(set(ranks))
    gaps = sum(1 for a, b in zip(distinct, distinct[1:]) if b - a <= 2)
    score += 0.04 * gaps                                      # connected ranks
    return max(0.0, min(1.0, score))


def mc_equity(hole, board, sims: int, rng: random.Random) -> float:
    """Equity against ONE random hand: deal the rest of the board and an
    opponent hand `sims` times and count wins (ties count half)."""
    dead = set(hole) | set(board)
    deck = [c for c in range(NUM_CARDS) if c not in dead]
    need = 5 - len(board)
    wins = 0.0
    for _ in range(sims):
        draw = rng.sample(deck, 5 + need)
        full = list(board) + draw[5:]
        mine = omaha_score(hole, full)
        theirs = omaha_score(draw[:5], full)
        if mine > theirs:
            wins += 1.0
        elif mine == theirs:
            wins += 0.5
    return wins / sims if sims else 0.5


def pot_odds(obs) -> float:
    """Share of the final pot we must put in to call."""
    if obs.to_call <= 0:
        return 0.0
    return obs.to_call / (obs.pot + obs.to_call)
