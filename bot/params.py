"""Every tunable number in one place, so the league tuner can override them.

Values are fractions of 1 unless noted. "pct" means preflop percentile
(share of starting hands that are weaker).
"""

DEFAULTS = {
    # --- preflop: button (small blind) first action -------------------
    "sb_fold_below": 0.10,       # fold the worst hands instead of completing
    "sb_raise_half_above": 0.50, # open half-pot with these
    "sb_raise_pot_above": 0.80,  # open pot with these
    # --- preflop: big blind after a limp -----------------------------
    "bb_raise_above": 0.70,
    # --- preflop: facing a raise ---------------------------------------
    "range_floor_1raise": 0.45,  # opponent's single raise = hands above this pct
    "range_floor_2raise": 0.70,  # a re-raise
    "range_floor_3raise": 0.85,  # three or more
    "pre_reraise_equity": 0.57,  # equity vs their range needed to re-raise
    "pre_call_margin_oop": 0.03, # extra equity over pot odds when out of position
    "pre_call_margin_ip": 0.00,
}


def make(overrides: dict | None = None) -> dict:
    params = dict(DEFAULTS)
    if overrides:
        unknown = set(overrides) - set(DEFAULTS)
        if unknown:
            raise KeyError(f"unknown params: {sorted(unknown)}")
        params.update(overrides)
    return params
