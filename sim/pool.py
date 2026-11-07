"""Name -> bot factory registry used by the simulator and the league."""

from __future__ import annotations

import os

from sim import opponents as opp
from sim.players import ROOT, BrainPlayer, agent_factory, class_factory, module_factory

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
    # Self-play: our own bot with features switched off, standing in for
    # earlier versions and for teams that build something close to us.
    for name, overrides in SELF_VARIANTS.items():
        bots[name] = class_factory(BrainPlayer, name, overrides=overrides)
    return bots


SELF_VARIANTS = {
    "self_static": {"learn_preflop": 0.0, "learn_postflop": 0.0},
    "self_learnpost": {"learn_postflop": 1.0},
    "self_nobluff": {"semi_bluff_freq": 0.0, "river_bluff_freq": 0.0},
    "self_norange": {"agg_bet": 0.0, "agg_raise": 0.0, "agg_reraise": 0.0, "agg_prev_street": 0.0,
                     "range_floor_call": 0.0},
    "self_loose": {"post_bet_eq": 0.55, "post_raise_eq": 0.66, "sb_raise_half_above": 0.35,
                   "semi_bluff_freq": 0.8, "river_bluff_freq": 0.2},
    "self_tight": {"post_bet_eq": 0.65, "post_raise_eq": 0.78, "sb_fold_below": 0.25,
                   "pre_call_margin_oop": 0.06},
}


def resolve(name: str):
    """A factory for a pool name, or for a path to an agent-style file."""
    bots = registry()
    if name in bots:
        return bots[name]
    if os.path.isfile(name):
        return module_factory(name)
    raise SystemExit(f"unknown bot {name!r}; known: {', '.join(sorted(bots))}")
