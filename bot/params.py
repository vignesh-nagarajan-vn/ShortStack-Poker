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
    # --- postflop: reading the opponent's range ----------------------
    "range_floor_call": 0.25,    # opponent called a preflop raise: drop their worst hands
    "agg_bet": 0.40,             # one bet this street = made-hand strength above this share
    "agg_raise": 0.62,           # a raise
    "agg_reraise": 0.78,         # two or more raises
    "agg_prev_street": 0.08,     # extra per earlier postflop street they bet
    "learn_preflop": 1.0,        # 1 = adapt preflop range floors to observed stats/showdowns
    "learn_postflop": 0.0,       # 1 = adapt postflop aggression levels too (off: lost in ablation)
    # --- postflop: our actions ----------------------------------------
    "post_bet_eq": 0.60,         # equity vs their range to bet when checked to
    "post_bet_eq_river": 0.63,
    "post_pot_size_eq": 0.75,    # bet/raise pot (not half) above this
    "post_raise_eq": 0.72,       # raise a bet
    "post_call_margin": 0.00,    # extra equity over pot odds to call
    "barrel_weight": 0.6,        # how much future bets raise the price of a call (x aggression x streets left)
    # --- low stack-to-pot ratio (40 bb stacks get committed fast) -------
    "commit_ratio": 0.5,         # rest <= this x pot after calling = treat as all-in
    "commit_shove_eq": 0.55,     # when committed, shove instead of calling above this
    "low_spr": 1.0,              # SPR below this: bet more hands for value/protection
    "low_spr_bet_eq": 0.53,
    # --- exploitation -----------------------------------------------------
    "exploit": 1.0,              # 1 = shift parameters by detected opponent profile (bot/profile.py)
    "autopilot_steal": 1.0,      # 1 = raise every hand into an opponent stuck on check/fold
    # --- draws and bluffs ----------------------------------------------
    "draw_credit": 0.60,         # opponent flush draws count as this strong when they bet
    "semi_bluff_min_eq": 0.38,   # semi-bluff draws with at least this equity
    "semi_bluff_freq": 0.50,     # how often we bet a qualifying draw when checked to
    "river_bluff_freq": 0.06,    # bet air on the river in position when checked to
    "river_bluff_max_eq": 0.25,
}


def make(overrides: dict | None = None) -> dict:
    params = dict(DEFAULTS)
    if overrides:
        unknown = set(overrides) - set(DEFAULTS)
        if unknown:
            raise KeyError(f"unknown params: {sorted(unknown)}")
        params.update(overrides)
    return params
