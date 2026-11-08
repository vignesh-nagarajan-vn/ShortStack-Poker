"""Draw detection under the Omaha "exactly 2 + 3" rule."""

from __future__ import annotations

import numpy as np

from evaluator import ACE


def flush_draw(holes: np.ndarray, board) -> np.ndarray:
    """(n, 5) hands -> 1.0 where the hand has two hole cards of a suit that
    already appears at least twice on a 3- or 4-card board (a flush draw
    under the 2 + 3 rule), else 0.0."""
    board = np.asarray(board, dtype=np.intp)
    board_suits = np.bincount(board & 3, minlength=4)          # (4,)
    out = np.zeros(len(holes), dtype=bool)
    if (board_suits >= 2).any():
        suits = holes & 3
        for s in np.flatnonzero(board_suits >= 2):             # at most 2 suits
            out |= (suits == s).sum(axis=1) >= 2
    return out.astype(np.float64)


def straight_window_count(hole, board) -> int:
    """How many 5-rank straight windows have >= 4 ranks covered using
    exactly 2 hole ranks and 2-3 board ranks: a rough open-ended draw count."""
    hole_ranks = {c >> 2 for c in hole}
    board_ranks = {c >> 2 for c in board}
    windows = [set(range(lo, lo + 5)) for lo in range(0, 5)] + [{ACE, 0, 1, 2, 3}]
    count = 0
    for w in windows:
        hb = len(w & board_ranks)
        hh = len(w & hole_ranks)
        if hb >= 2 and hh >= 2 and min(hh, 2) + min(hb, 3) >= 4:
            count += 1
    return count


def has_draw(hole, board) -> bool:
    """True if our hand has a flush draw or two open straight windows."""
    if len(board) >= 5:
        return False
    fd = flush_draw(np.asarray([hole], dtype=np.intp), board)[0] > 0
    return bool(fd) or straight_window_count(hole, board) >= 2
