"""Paired A/B test: candidate parameter sets vs the baseline, same seeds.

    python -m sim.ab --cand thin_river_shift=0.2 --seeds 1 2 3 4
    python -m sim.ab --cand big:thin_river_shift=0.2 --cand small:thin_river_shift=0.15
    python -m sim.ab --cand x=1 --base learn_postflop=1 --opps mc_basic brown

Every arm is our bot (BrainPlayer, safety wrapper included) with parameter
overrides. Each arm plays every opponent in the pool on the same seeds, so
both see the same cards (common random numbers). For each opponent we print
both arms' bb/deal and the difference; the pool mean difference gets two
standard errors:

  se_seed  from the spread of per-seed pool means (honest, coarse)
  se_deal  from the per-deal paired differences, matched by opponent, seed
           and deal (tighter; deals inside a match are not fully
           independent because the bot learns, so treat it as a floor)

"field" means every opponent except our own self-play variants (self_*,
agent), which mostly measure noise. Baseline runs are cached in
results/ab_cache, keyed by a hash of bot/, sim/ and data/, so a series of
candidates against one baseline pays for it once.

Keep rule (docs/experiments.md): pool mean diff >= +0.05 bb/deal, more than
~2 SE from zero, and no field opponent worse by more than 0.3 bb/deal.
"""

from __future__ import annotations

import os

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import argparse  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import statistics  # noqa: E402
import time  # noqa: E402
from concurrent.futures import ProcessPoolExecutor, as_completed  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(ROOT, "results", "ab_cache")
SELF_PREFIXES = ("self_", "agent")


def is_self(name: str) -> bool:
    return name.startswith(SELF_PREFIXES)


def code_hash() -> str:
    """Hash of everything that changes how matches play out."""
    h = hashlib.sha1()
    sim_play = ("heuristics.py", "opponents.py", "players.py", "pool.py", "run_match.py")
    for sub in ("bot", "sim", "data"):
        folder = os.path.join(ROOT, sub)
        for name in sorted(os.listdir(folder)):
            path = os.path.join(folder, name)
            if sub == "sim" and name not in sim_play:
                continue
            if os.path.isfile(path) and not name.endswith(".pyc"):
                h.update(name.encode())
                with open(path, "rb") as f:
                    h.update(f.read())
    return h.hexdigest()[:12]


def parse_overrides(spec: str) -> tuple[str, dict]:
    """'name:k=v,k2=v2' or 'k=v,k2=v2' or a JSON object -> (label, overrides)."""
    label = None
    if ":" in spec and not spec.lstrip().startswith("{"):
        label, spec = spec.split(":", 1)
    spec = spec.strip()
    if not spec:
        return label or "base", {}
    if spec.startswith("{"):
        overrides = json.loads(spec)
    else:
        overrides = {}
        for part in spec.split(","):
            k, v = part.split("=", 1)
            overrides[k.strip()] = float(v)
    return label or ",".join(f"{k}={v:g}" for k, v in overrides.items()), overrides


def _job(job: tuple) -> dict:
    arm, overrides, opp, seed, deals = job
    from bot.params import make
    from sim.players import BrainPlayer, class_factory
    from sim.pool import resolve
    from sim.run_match import play_match
    from game import BIG_BLIND

    make(overrides)                      # fail fast on unknown params
    me = class_factory(BrainPlayer, arm, overrides=overrides)
    start = time.perf_counter()
    out = play_match(me, resolve(opp), seed, deals)
    h1, h2 = out.halves
    paired = [(a + b) / BIG_BLIND for a, b in zip(h1.nets_a, h2.nets_a)]
    return {
        "arm": arm, "opp": opp, "seed": str(seed), "mean": out.mean_bb, "paired": paired,
        "time_a": max(h.stats["A"].time_seconds for h in out.halves),
        "errors_a": sum(h.stats["A"].errors for h in out.halves),
        "opp_bank_empty": sum(h.stats["B"].bank_empty for h in out.halves),
        "wall": time.perf_counter() - start,
    }


def _cache_path(key: str) -> str:
    return os.path.join(CACHE_DIR, hashlib.sha1(key.encode()).hexdigest()[:20] + ".json")


def run_arms(arms: dict, opps: list[str], seeds: list[str], deals: int, workers: int,
             base_label: str, use_cache: bool = True, verbose: bool = False) -> dict:
    """Play every (arm, opponent, seed). Returns {arm: {(opp, seed): result}}."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    chash = code_hash()
    out: dict = {arm: {} for arm in arms}
    jobs, keys = [], {}
    for arm, overrides in arms.items():
        for opp in opps:
            for seed in seeds:
                key = json.dumps([chash, overrides, opp, seed, deals], sort_keys=True)
                path = _cache_path(key)
                if use_cache and arm == base_label and os.path.isfile(path):
                    with open(path, encoding="utf-8") as f:
                        out[arm][(opp, seed)] = json.load(f)
                    continue
                job = (arm, overrides, opp, seed, deals)
                jobs.append(job)
                keys[(arm, opp, seed)] = path
    if jobs:
        print(f"running {len(jobs)} matches on {workers} workers "
              f"({sum(len(v) for v in out.values())} cached)", flush=True)
    start = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_job, j) for j in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            r = fut.result()
            out[r["arm"]][(r["opp"], r["seed"])] = r
            if r["arm"] == base_label:
                with open(keys[(r["arm"], r["opp"], r["seed"])], "w", encoding="utf-8") as f:
                    json.dump(r, f)
            if verbose or i % max(1, len(jobs) // 10) == 0:
                print(f"  {i}/{len(jobs)} done ({time.perf_counter() - start:.0f}s)", flush=True)
    return out


def compare(base: dict, cand: dict, opps: list[str], seeds: list[str]) -> dict:
    """Per-opponent and pool statistics of cand - base."""
    rows = []
    for opp in opps:
        b = [base[(opp, s)]["mean"] for s in seeds]
        c = [cand[(opp, s)]["mean"] for s in seeds]
        d = [x - y for x, y in zip(c, b)]
        # per-deal SE of this opponent's mean diff
        diffs = [x - y for s in seeds for x, y in zip(cand[(opp, s)]["paired"], base[(opp, s)]["paired"])]
        se = statistics.stdev(diffs) / math.sqrt(len(diffs)) if len(diffs) > 1 else 0.0
        rows.append({"opp": opp, "base": sum(b) / len(b), "cand": sum(c) / len(c),
                     "diff": sum(d) / len(d), "se": se,
                     "tcand": max(cand[(opp, s)]["time_a"] for s in seeds),
                     "err": sum(cand[(opp, s)]["errors_a"] for s in seeds),
                     "drain_b": sum(base[(opp, s)]["opp_bank_empty"] for s in seeds),
                     "drain_c": sum(cand[(opp, s)]["opp_bank_empty"] for s in seeds)})

    def pool_stats(names):
        sel = [r for r in rows if r["opp"] in names]
        if not sel:
            return 0.0, 0.0, 0.0
        mean = sum(r["diff"] for r in sel) / len(sel)
        se_deal = math.sqrt(sum(r["se"] ** 2 for r in sel)) / len(sel)
        per_seed = [sum(cand[(o, s)]["mean"] - base[(o, s)]["mean"] for o in names) / len(names)
                    for s in seeds]
        se_seed = statistics.stdev(per_seed) / math.sqrt(len(seeds)) if len(seeds) > 1 else float("nan")
        return mean, se_seed, se_deal

    field = [o for o in opps if not is_self(o)]
    return {"rows": rows, "all": pool_stats(opps), "field": pool_stats(field)}


def report(label: str, stats: dict) -> str:
    lines = [f"\n=== {label} ===",
             f"{'opponent':<24}{'base':>9}{'cand':>9}{'diff':>9}{'se':>7}{'t_max':>7}{'drain b/c':>11}"]
    for r in stats["rows"]:
        flag = "  <-- drop" if r["diff"] < -0.3 and not is_self(r["opp"]) else ""
        err = f"  ERR={r['err']}" if r["err"] else ""
        lines.append(f"{r['opp']:<24}{r['base']:>+9.3f}{r['cand']:>+9.3f}{r['diff']:>+9.3f}"
                     f"{r['se']:>7.3f}{r['tcand']:>7.2f}{r['drain_b']:>6}/{r['drain_c']:<4}{flag}{err}")
    for name in ("all", "field"):
        m, ss, sd = stats[name]
        lines.append(f"{'POOL ' + name:<24}{'':>18}{m:>+9.3f}   se_seed={ss:.3f} se_deal={sd:.3f}"
                     f"  z={m / max(ss if ss == ss else 0, sd, 1e-9):+.1f}")
    worst = min((r for r in stats["rows"] if not is_self(r["opp"])), key=lambda r: r["diff"], default=None)
    m, ss, sd = stats["all"]
    se = max(ss if ss == ss else 0.0, sd)
    keep = m >= 0.05 and m > 2 * se and (worst is None or worst["diff"] >= -0.3)
    lines.append(f"verdict: {'KEEP' if keep else 'reject'} "
                 f"(worst field opp {worst['opp']} {worst['diff']:+.3f})" if worst else "")
    return "\n".join(lines)


def main() -> None:
    from sim.pool import registry

    parser = argparse.ArgumentParser(description="Paired A/B of parameter sets against the pool.")
    parser.add_argument("--cand", action="append", required=True,
                        help="'label:k=v,k2=v2' or JSON; repeat for several candidates")
    parser.add_argument("--base", default="", help="baseline overrides (default: current DEFAULTS)")
    parser.add_argument("--opps", nargs="*", help="opponents (default: whole pool)")
    parser.add_argument("--skip", nargs="*", default=[], help="opponents to leave out")
    parser.add_argument("--seeds", nargs="+", default=["101", "102", "103", "104"])
    parser.add_argument("--deals", type=int, default=1000)
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()

    opps = args.opps or sorted(n for n in registry() if not n.startswith("x_"))
    opps = [o for o in opps if o not in args.skip]
    base_label, base_over = parse_overrides(args.base)
    base_label = "BASE"
    arms = {base_label: base_over}
    for spec in args.cand:
        label, over = parse_overrides(spec)
        arms[label] = over
    start = time.perf_counter()
    res = run_arms(arms, opps, args.seeds, args.deals, args.workers, base_label, not args.no_cache)
    log_lines = [f"# {time.strftime('%Y-%m-%d %H:%M')} seeds={' '.join(args.seeds)} deals={args.deals} "
                 f"base={json.dumps(base_over)} code={code_hash()}"]
    for label, over in arms.items():
        if label == base_label:
            continue
        text = report(f"{label}  {json.dumps(over)}", compare(res[base_label], res[label], opps, args.seeds))
        print(text, flush=True)
        log_lines.append(text)
    print(f"\n{time.perf_counter() - start:.0f}s")
    with open(os.path.join(ROOT, "results", "ab.log"), "a", encoding="utf-8") as f:
        f.write("\n".join(log_lines) + "\n\n")


if __name__ == "__main__":
    main()
