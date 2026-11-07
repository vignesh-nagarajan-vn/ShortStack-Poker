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
