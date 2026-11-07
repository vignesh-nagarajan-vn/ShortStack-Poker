"""Rebuild data/fasteval_tables.npz (the numpy Omaha rank table).

    python tools/build_tables.py

Run it again only if evaluator.py's hand ranking ever changes.
tests/test_fasteval.py checks the shipped file against a fresh build.
"""

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np  # noqa: E402

from bot.fasteval import TABLE_PATH, build_rank_tables  # noqa: E402

if __name__ == "__main__":
    start = time.perf_counter()
    rank, by_colex, distinct = build_rank_tables()
    os.makedirs(os.path.dirname(TABLE_PATH), exist_ok=True)
    np.savez_compressed(TABLE_PATH, rank=rank, rank_by_colex=by_colex, distinct=distinct)
    size = os.path.getsize(TABLE_PATH) / 1e6
    print(f"wrote {TABLE_PATH} ({size:.1f} MB) in {time.perf_counter() - start:.1f}s")
