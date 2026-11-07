"""Timing benchmark for the evaluators and the equity engine.

    python -m sim.bench
"""

from __future__ import annotations

import random
import time

from sim.players import ROOT  # noqa: F401  (sets sys.path)
from bot.equity import EquityEngine
from evaluator import omaha_score, warmup


def _time(fn, reps: int) -> float:
    fn()
    start = time.perf_counter()
    for _ in range(reps):
        fn()
    return (time.perf_counter() - start) / reps


def main() -> None:
    warmup()
    rng = random.Random(1)
    cards = rng.sample(range(36), 10)
    print(f"omaha_score:            {_time(lambda: omaha_score(cards[:5], cards[5:]), 5000) * 1e6:8.1f} us")
    eng = EquityEngine(0)
    hole = cards[:5]
    for street, board in (("preflop", []), ("flop", cards[5:8]), ("turn", cards[5:9]),
                          ("river", cards[5:10])):
        for n in (100, 300, 1000):
            t = _time(lambda: eng.equity(hole, board, n), 200)
            print(f"equity {street:<7} n={n:<5}  {t * 1e3:8.3f} ms   ({t / n * 1e6:.2f} us/sample)")


if __name__ == "__main__":
    main()
