"""Classify the opponent and shift our parameters to exploit it.

Profiles (checked in this order, from the shrunk opponent rates):

  maniac   raises/bets most of the time   -> never bluff, raise strong hands
                                             for value, let them bet into us
  nit      folds to bets / plays few hands -> steal: open wider, bluff and
                                             semi-bluff much more
  station  almost never folds              -> no bluffs, value-bet thinner
  honest   rarely bets                     -> their bets mean strength: give
                                             their bets more credit

Hysteresis: a new profile must win two evaluations in a row (every 20
hands after a 40-hand warm-up) before we switch, so noise near a boundary
doesn't make us flip-flop, and so we're hard to read in return.
"""

from __future__ import annotations

WARMUP_HANDS = 40
EVERY = 20

# ("add", x) shifts the base value, ("set", x) replaces it.
ADJUST = {
    "maniac": {"river_bluff_freq": ("set", 0.0), "semi_bluff_freq": ("set", 0.15),
               "post_raise_eq": ("add", -0.04), "post_bet_eq": ("add", 0.03)},
    "nit": {"sb_raise_half_above": ("add", -0.25), "sb_fold_below": ("set", 0.02),
            "river_bluff_freq": ("set", 0.30), "semi_bluff_freq": ("set", 0.85),
            "post_bet_eq": ("add", -0.04)},
    "station": {"river_bluff_freq": ("set", 0.0), "semi_bluff_freq": ("set", 0.2),
                "post_bet_eq": ("add", -0.04), "post_bet_eq_river": ("add", -0.05)},
    "honest": {"agg_bet": ("add", 0.10), "agg_raise": ("add", 0.08),
               "river_bluff_freq": ("add", 0.04)},
    "default": {},
}


def classify(opp) -> str:
    agg, pfr = opp.rate("aggression"), opp.rate("pfr")
    ftb, vpip = opp.rate("fold_to_bet"), opp.rate("vpip")
    if agg > 0.55 or pfr > 0.65:
        return "maniac"
    if ftb > 0.58 or vpip < 0.40:
        return "nit"
    if ftb < 0.18:
        return "station"
    if agg < 0.22:
        return "honest"
    return "default"


def apply(base: dict, profile: str) -> dict:
    params = dict(base)
    for key, (op, value) in ADJUST.get(profile, {}).items():
        params[key] = params[key] + value if op == "add" else value
    return params


class Profiler:
    def __init__(self, base: dict) -> None:
        self.base = base
        self.profile = "default"
        self.candidate = "default"
        self.streak = 0
        self.params = dict(base)

    def update(self, opp) -> bool:
        """Re-classify if it's time. Returns True if the profile changed."""
        if opp.hands < WARMUP_HANDS or opp.hands % EVERY:
            return False
        new = classify(opp)
        if new == self.profile:
            self.candidate, self.streak = new, 0
            return False
        self.streak = self.streak + 1 if new == self.candidate else 1
        self.candidate = new
        if self.streak >= 2:
            self.profile, self.streak = new, 0
            self.params = apply(self.base, new)
            return True
        return False
