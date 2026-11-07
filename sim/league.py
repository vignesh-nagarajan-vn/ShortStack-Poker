"""Round-robin league over the opponent pool, run in parallel.

    python -m sim.league --focus agent --deals 1000 --seeds 1 2 3
    python -m sim.league --bots agent mc_random nit --deals 500

--focus X plays only X against every other bot (what we usually want);
without it every pair plays. Each (pair, seed) is one duplicate match, run
in its own worker process. The table ranks bots by tournament points, then
by average bb/deal, exactly like the tournament standings.
"""

from __future__ import annotations

import argparse
import itertools
import os
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed


def _run(job: tuple[str, str, str, int]) -> dict:
    """Worker: play one duplicate match by bot names (names pickle, factories don't)."""
    from sim.pool import resolve
    from sim.run_match import play_match

    a, b, seed, deals = job
    out = play_match(resolve(a), resolve(b), seed, deals)
    stats_a = [h.stats["A"] for h in out.halves]
    stats_b = [h.stats["B"] for h in out.halves]
    return {
        "a": a, "b": b, "seed": seed, "mean": out.mean_bb, "ci": out.ci,
        "verdict": out.verdict, "points_a": out.points_a,
        "time_a": max(s.time_seconds for s in stats_a),
        "time_b": max(s.time_seconds for s in stats_b),
        "errors_a": sum(s.errors for s in stats_a), "errors_b": sum(s.errors for s in stats_b),
        "first_error_a": next((s.first_error for s in stats_a if s.first_error), ""),
        "first_error_b": next((s.first_error for s in stats_b if s.first_error), ""),
    }


def run_league(bots: list[str], seeds: list[str], deals: int, focus: str | None = None,
               workers: int | None = None, verbose: bool = True) -> list[dict]:
    """Play every scheduled match and return the raw results."""
    if focus:
        pairs = [(focus, b) for b in bots if b != focus]
    else:
        pairs = list(itertools.combinations(bots, 2))
    jobs = [(a, b, str(s), deals) for a, b in pairs for s in seeds]
    results = []
    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_run, job) for job in jobs]
        for fut in as_completed(futures):
            r = fut.result()
            results.append(r)
            if verbose:
                err = f" A-ERR: {r['first_error_a']}" if r["errors_a"] else ""
                print(f"  {r['a']:>22} vs {r['b']:<22} seed={r['seed']:<4} "
                      f"{r['mean']:+7.3f} bb/deal [{r['ci'][0]:+.2f},{r['ci'][1]:+.2f}] "
                      f"{r['verdict']:<5} tA={r['time_a']:.2f}s{err}", flush=True)
    return results


def table(results: list[dict]) -> str:
    """Standings: points, then average bb/deal (the tournament's ordering)."""
    pts: dict[str, float] = defaultdict(float)
    bb: dict[str, list[float]] = defaultdict(list)
    rec: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    worst_time: dict[str, float] = defaultdict(float)
    errors: dict[str, int] = defaultdict(int)
    for r in results:
        a, b = r["a"], r["b"]
        pts[a] += r["points_a"]
        pts[b] += 1.0 - r["points_a"] if r["verdict"] != "BOTH_FORFEIT" else 0.0
        bb[a].append(r["mean"])
        bb[b].append(-r["mean"])
        idx = {"A": (0, 2), "B": (2, 0), "CHOP": (1, 1), "BOTH_FORFEIT": (2, 2)}[r["verdict"]]
        rec[a][idx[0]] += 1
        rec[b][idx[1]] += 1
        worst_time[a] = max(worst_time[a], r["time_a"])
        worst_time[b] = max(worst_time[b], r["time_b"])
        errors[a] += r["errors_a"]
        errors[b] += r["errors_b"]
    rows = sorted(pts, key=lambda n: (pts[n], sum(bb[n]) / len(bb[n])), reverse=True)
    lines = [f"{'bot':<26}{'points':>8}{'W-C-L':>10}{'bb/deal':>10}{'max s/half':>12}{'errors':>8}"]
    for n in rows:
        w, c, l = rec[n]
        lines.append(f"{n:<26}{pts[n]:>8.1f}{f'{w}-{c}-{l}':>10}{sum(bb[n]) / len(bb[n]):>+10.3f}"
                     f"{worst_time[n]:>12.2f}{errors[n]:>8}")
    return "\n".join(lines)


def main() -> None:
    from sim.pool import registry

    parser = argparse.ArgumentParser(description="Round-robin league over the opponent pool.")
    parser.add_argument("--bots", nargs="*", help="bot names (default: the whole pool)")
    parser.add_argument("--focus", help="only play this bot against every other bot")
    parser.add_argument("--seeds", nargs="+", default=["1", "2", "3"])
    parser.add_argument("--deals", type=int, default=1000)
    parser.add_argument("--workers", type=int)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    bots = args.bots or sorted(registry())
    if args.focus and args.focus not in bots:
        bots.append(args.focus)
    start = time.perf_counter()
    results = run_league(bots, args.seeds, args.deals, args.focus, args.workers, not args.quiet)
    print()
    print(table(results))
    print(f"\n{len(results)} matches in {time.perf_counter() - start:.1f}s")


if __name__ == "__main__":
    main()
