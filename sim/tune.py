"""Coordinate-search parameter tuning against the opponent pool.

    python -m sim.tune --rounds 2 --seeds 11 12 --deals 1000

Each candidate parameter set plays our bot (BrainPlayer with overrides)
against every opponent in TUNING_POOL on the same seeds (common random
numbers, so candidates face identical cards). Score = tournament points,
then average bb/deal. For each parameter in turn we try a step down and a
step up and keep a change only if it beats the incumbent by MIN_GAIN bb,
which guards against chasing noise. Results append to results/tune.log.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ProcessPoolExecutor

TUNING_POOL = ["mc_basic", "mc_tight", "mc_loose", "mc_half", "adaptive", "adaptive_loose",
               "maniac", "nit", "baseline_always_pot", "weak_tight", "self_static"]

# name: (step, low, high)
SEARCH = {
    "post_bet_eq": (0.03, 0.50, 0.72),
    "post_raise_eq": (0.04, 0.60, 0.85),
    "post_pot_size_eq": (0.05, 0.60, 0.90),
    "sb_raise_half_above": (0.10, 0.20, 0.80),
    "sb_fold_below": (0.05, 0.0, 0.30),
    "bb_raise_above": (0.08, 0.45, 0.90),
    "pre_reraise_equity": (0.03, 0.50, 0.66),
    "barrel_weight": (0.2, 0.0, 1.2),
    "semi_bluff_freq": (0.2, 0.0, 1.0),
    "river_bluff_freq": (0.05, 0.0, 0.3),
    "commit_shove_eq": (0.04, 0.45, 0.65),
    "agg_bet": (0.08, 0.20, 0.65),
}
MIN_GAIN = 0.08


def _match(job) -> dict:
    overrides, opp, seed, deals = job
    from sim.players import BrainPlayer, class_factory
    from sim.pool import resolve
    from sim.run_match import play_match
    me = class_factory(BrainPlayer, "candidate", overrides=overrides)
    out = play_match(me, resolve(opp), seed, deals)
    return {"opp": opp, "seed": seed, "mean": out.mean_bb, "points": out.points_a}


def evaluate(pool: ProcessPoolExecutor, overrides: dict, seeds, deals) -> tuple[float, float]:
    jobs = [(overrides, opp, s, deals) for opp in TUNING_POOL for s in seeds]
    res = list(pool.map(_match, jobs))
    points = sum(r["points"] for r in res)
    bb = sum(r["mean"] for r in res) / len(res)
    return points, bb


def main() -> None:
    from bot.params import DEFAULTS

    parser = argparse.ArgumentParser(description="Tune bot parameters against the pool.")
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--seeds", nargs="+", default=["11", "12"])
    parser.add_argument("--deals", type=int, default=1000)
    parser.add_argument("--params", nargs="*", default=list(SEARCH))
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    args = parser.parse_args()

    os.makedirs("results", exist_ok=True)
    log = open(os.path.join("results", "tune.log"), "a", encoding="utf-8")

    def say(msg: str) -> None:
        print(msg, flush=True)
        log.write(msg + "\n")
        log.flush()

    best: dict = {}
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        start = time.perf_counter()
        best_pts, best_bb = evaluate(pool, best, args.seeds, args.deals)
        say(f"baseline: points={best_pts} bb={best_bb:+.3f} ({time.perf_counter() - start:.0f}s)")
        for rnd in range(args.rounds):
            for name in args.params:
                step, lo, hi = SEARCH[name]
                cur = best.get(name, DEFAULTS[name])
                for val in (round(cur - step, 4), round(cur + step, 4)):
                    if not lo <= val <= hi:
                        continue
                    cand = dict(best, **{name: val})
                    pts, bb = evaluate(pool, cand, args.seeds, args.deals)
                    better = pts > best_pts or (pts == best_pts and bb > best_bb + MIN_GAIN)
                    say(f"r{rnd} {name}={val}: points={pts} bb={bb:+.3f}"
                        f"{'  <-- keep' if better else ''}")
                    if better:
                        best, best_pts, best_bb = cand, pts, bb
                        break
        say("BEST " + json.dumps(best, sort_keys=True) + f" points={best_pts} bb={best_bb:+.3f}")


if __name__ == "__main__":
    main()
