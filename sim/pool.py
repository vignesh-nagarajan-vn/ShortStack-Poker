"""Name -> bot factory registry used by the simulator and the league."""

from __future__ import annotations

import os

from sim import opponents as opp
from sim.players import ROOT, agent_factory, class_factory, module_factory

BASELINES = ("baseline_random", "baseline_calling_station", "baseline_always_half",
             "baseline_always_pot")


def registry() -> dict:
    """All bots the simulator knows about, by name."""
    bots = {"agent": agent_factory()}
    for name in BASELINES:
        bots[name] = module_factory(os.path.join(ROOT, "baseline-bots", f"{name}.py"), name)
    simple = {
        "checkfold": (opp.CheckFold, {}),
        "guide_example": (opp.GuideExample, {}),
        "nit": (opp.Nit, {}),
        "maniac": (opp.Maniac, {}),
        "weak_tight": (opp.WeakTight, {}),
        # "MC equity vs one random hand" family: the likely bulk of the field.
        "mc_basic": (opp.McThreshold, {}),
        "mc_tight": (opp.McThreshold, {"raise_thr": 0.7, "bet_thr": 0.6, "margin": 0.05}),
        "mc_loose": (opp.McThreshold, {"raise_thr": 0.6, "bet_thr": 0.5, "margin": -0.03,
                                       "bluff": 0.1}),
        "mc_half": (opp.McThreshold, {"half_size": True, "bluff": 0.05}),
        "mc_drain": (opp.McThreshold, {"sims": 40}),     # slightly too slow: bank runs out late
        "mc_greedy": (opp.McThreshold, {"sims": 300}),   # far too slow: bank runs out early
        # Adaptive bots that model and exploit their opponent.
        "adaptive": (opp.AdaptiveExploiter, {}),
        "adaptive_loose": (opp.AdaptiveExploiter, {"raise_thr": 0.6, "bet_thr": 0.5, "bluff": 0.1}),
    }
    for name, (cls, kwargs) in simple.items():
        bots[name] = class_factory(cls, name, **kwargs)
    return bots


def resolve(name: str):
    """A factory for a pool name, or for a path to an agent-style file."""
    bots = registry()
    if name in bots:
        return bots[name]
    if os.path.isfile(name):
        return module_factory(name)
    raise SystemExit(f"unknown bot {name!r}; known: {', '.join(sorted(bots))}")
