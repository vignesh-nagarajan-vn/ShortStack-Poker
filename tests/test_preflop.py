"""The shipped preflop table loads, is sane and keeps startup fast."""

import os
import subprocess
import sys
import time

import numpy as np

from bot import preflop
from bot.equity import EquityEngine
from evaluator import cards_from_str

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_table_is_shipped_and_loaded():
    assert preflop.available, "data/preflop_equity.npz is missing"
    assert 0.45 < float(np.median(preflop.EQUITY)) < 0.55


def test_suit_renaming_does_not_change_equity():
    a = cards_from_str("Ah Kh Qd Jd 9c")
    b = cards_from_str("As Ks Qc Jc 9h")
    assert preflop.equity(a) == preflop.equity(b)


def test_good_hand_beats_bad_hand():
    good = cards_from_str("Ah Ad Kh Kd Qs")
    bad = cards_from_str("6c 6d 6h 6s 7c")
    assert preflop.percentile(good) > 0.9
    assert preflop.percentile(bad) < 0.1


def test_table_agrees_with_fresh_simulation():
    eng = EquityEngine(8)
    rng = np.random.default_rng(1)
    for _ in range(5):
        hole = rng.permutation(36)[:5].tolist()
        assert abs(preflop.equity(hole) - eng.equity(hole, [], 20000)) < 0.02


def test_batch_matches_single():
    rng = np.random.default_rng(2)
    holes = np.array([rng.permutation(36)[:5] for _ in range(50)])
    batch = preflop.percentile_batch(holes)
    for h, p in zip(holes, batch):
        assert p == preflop.percentile(h.tolist())


def test_agent_imports_quickly():
    # The server must answer within 15 s of starting; leave a wide margin
    # for a slower tournament machine.
    start = time.perf_counter()
    subprocess.run([sys.executable, "-c", "import agent"], cwd=ROOT, check=True)
    assert time.perf_counter() - start < 6.0
