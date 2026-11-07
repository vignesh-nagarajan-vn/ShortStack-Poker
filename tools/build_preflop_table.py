"""Build data/preflop_equity.npz: equity vs a random hand for every hand.

    python tools/build_preflop_table.py --samples 4000

There are C(36, 5) = 376,992 five-card hands, but suits are symmetric, so
hands that differ only by renaming suits have the same equity. We map each
hand to a canonical representative (lexicographically smallest over the 24
suit permutations), simulate each distinct class once with many samples
across all CPU cores, and store the result for every hand by colex index.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from itertools import combinations, permutations

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np  # noqa: E402

OUT_PATH = os.path.join(ROOT, "data", "preflop_equity.npz")


def all_hands() -> np.ndarray:
    """Every 5-card hand in colex order (row i has colex index i)."""
    from bot.fasteval import colex_index
    hands = np.array(list(combinations(range(36), 5)), dtype=np.int64)
    order = np.argsort(colex_index(hands))
    return hands[order]


def canonical_ids(hands: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(class id per hand, one representative hand per class)."""
    from bot.fasteval import colex_index
    ranks, suits = hands >> 2, hands & 3
    best = None
    for perm in permutations(range(4)):
        mapped = (ranks << 2) | np.array(perm)[suits]
        mapped.sort(axis=1)
        idx = colex_index(mapped)
        best = idx if best is None else np.minimum(best, idx)
    classes, class_of = np.unique(best, return_inverse=True)
    reps = hands[classes]           # hands are in colex order, so index == colex id
    return class_of, reps


def _work(args) -> list[float]:
    reps, samples, seed = args
    from bot.equity import EquityEngine
    eng = EquityEngine(seed)
    return [eng.equity(h, [], samples) for h in reps]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the preflop equity table.")
    parser.add_argument("--samples", type=int, default=4000, help="Monte Carlo samples per class")
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    args = parser.parse_args()

    start = time.perf_counter()
    hands = all_hands()
    class_of, reps = canonical_ids(hands)
    print(f"{len(hands)} hands -> {len(reps)} suit-isomorphic classes "
          f"({time.perf_counter() - start:.1f}s)", flush=True)

    chunks = np.array_split(np.arange(len(reps)), args.workers * 8)
    jobs = [(reps[c].tolist(), args.samples, 1000 + i) for i, c in enumerate(chunks)]
    equities = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for i, part in enumerate(pool.map(_work, jobs)):
            equities.extend(part)
            if (i + 1) % args.workers == 0:
                print(f"  {len(equities)}/{len(reps)} classes", flush=True)
    class_eq = np.array(equities, dtype=np.float64)
    hand_eq = class_eq[class_of]
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    np.savez_compressed(OUT_PATH, equity=np.round(hand_eq * 65535).astype(np.uint16),
                        samples=np.array([args.samples]))
    print(f"wrote {OUT_PATH} ({os.path.getsize(OUT_PATH) / 1e6:.2f} MB): "
          f"min {hand_eq.min():.3f} median {np.median(hand_eq):.3f} max {hand_eq.max():.3f} "
          f"in {time.perf_counter() - start:.0f}s")


if __name__ == "__main__":
    main()
