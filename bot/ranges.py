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
from bot.draws import flush_draw

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
    made = fe.pair_best(fe.board_triples_partial(board))[fe.hole_pairs(opp)].max(axis=1)
    order = made.argsort(kind="stable")
    rank = np.empty(len(opp), dtype=np.float64)
    rank[order] = np.arange(len(opp))
    return rank / max(1, len(opp) - 1)


def action_weight(board, pre_floor: float, actions, softness: float = 0.12,
                  draw_credit: float = 0.6, check_weight: float = 0.35):
    """Opponent hands that fit every postflop action they took this hand,
    each read through how often this opponent takes it in that spot.

    `actions` is a list of (street, kind, freq):
      ("bet", f)   they bet/raised; they do that f of the time there, so the
                   hand sits in roughly their top f (made strength on that
                   street's board, flush draws credited before the river)
      ("call", q)  they called a bet they fold q of the time: above their
                   fold line
      ("check", f) they checked where they bet f of the time: slightly
                   fewer strong hands (they may slow-play, so only
                   `check_weight` of the bet filter is applied)
    Every factor is soft and floored, so a misread never rules a hand out.
    """
    board = list(board)
    if pre_floor <= 0 and not actions:
        return None

    def weight(opp: np.ndarray) -> np.ndarray:
        w = np.ones(len(opp))
        if pre_floor > 0:
            pct = preflop.percentile_batch(opp)
            w *= np.maximum(_sigmoid((pct - pre_floor) / 0.06), FLOOR_WEIGHT)
        cache = {}
        for street, kind, freq in actions:
            if street not in cache:
                b = board[:street + 2]
                s = made_strength(opp, b)
                if len(b) < 5 and draw_credit > 0:
                    s = np.maximum(s, draw_credit * flush_draw(opp, b))
                cache[street] = s
            s = cache[street]
            if kind == "bet":
                w *= np.maximum(_sigmoid((s - (1.0 - freq)) / softness), 0.09)
            elif kind == "call":
                w *= np.maximum(_sigmoid((s - freq) / softness), 0.15)
            else:
                w *= 1.0 - check_weight * _sigmoid((s - (1.0 - freq)) / softness)
        return w

    return weight


def postflop_weight(board, pre_floor: float, aggression: float, softness: float = 0.12,
                    draw_credit: float = 0.6):
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
            if len(board) < 5 and draw_credit > 0:
                # Bettors also hold draws: a flush draw counts as a decent hand.
                strength = np.maximum(strength, draw_credit * flush_draw(opp, board))
            w *= np.maximum(_sigmoid((strength - aggression) / softness), FLOOR_WEIGHT)
        return w

    if pre_floor <= 0 and aggression <= 0:
        return None
    return weight
