"""Every tunable number in one place, so the league tuner can override them.

Values are fractions of 1 unless noted. "pct" means preflop percentile
(share of starting hands that are weaker).
"""

DEFAULTS = {
    # --- preflop: button (small blind) first action -------------------
    "sb_fold_below": 0.05,       # fold the worst hands instead of completing (tuned from 0.10)
    "sb_raise_half_above": 0.60, # open half-pot with these (tuned from 0.50)
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
    "agg_prev_adapt": 1.0,       # 1 = earlier-street bets add strength only as far as their betting is selective (A/B +0.12)
    "learn_postflop": 1.0,       # 1 = adapt postflop aggression levels too (A/B +0.14 bb/deal, 8 seeds)
    # --- postflop: our actions ----------------------------------------
    "post_bet_eq": 0.60,         # equity vs their range to bet when checked to
    "post_bet_eq_river": 0.63,
    "thin_river_shift": 0.10,    # max drop in the river bet threshold vs loose river callers
    "thin_river_from": 0.70,     # our called river bets winning this often starts the drop...
    "thin_river_full": 0.85,     # ...and this often applies all of it
    "thin_river_min": 10,        # called river bets seen before it can apply
    "thin_river_raise": 0.0,     # 1 = also lower the river raise bar by the same shift
    "river_value_range": 0.0,    # 1 = value-bet the river by equity vs their learned calling range
    "river_value_need": 0.55,    # ...betting when we win at least this often once called
    "river_call_min": 8,         # showdowns of called river bets needed before it applies
    "post_pot_size_eq": 0.75,    # bet/raise pot (not half) above this
    "post_raise_eq": 0.68,       # raise a bet (tuned from 0.72)
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
    # --- our own image (bot/image.py) ----------------------------------
    "image_ftb_cap": 0.50,       # keep our fold-to-bet below adaptive bots' bluff trigger
    "image_call_bonus": 0.04,    # equity we give up on marginal calls while above it...
    "image_attack_gap": 0.08,    # ...and the opponent's recent aggression is this far above its average
    "image_agg_cap": 0.45,       # above this aggression, halve our bluffs
    # --- draws and bluffs ----------------------------------------------
    "draw_credit": 0.60,         # opponent flush draws count as this strong when they bet
    "semi_bluff_min_eq": 0.38,   # semi-bluff draws with at least this equity
    "semi_bluff_freq": 0.50,     # how often we bet a qualifying draw when checked to
    "river_bluff_freq": 0.06,    # bet air on the river in position when checked to
    "river_bluff_max_eq": 0.25,
    "draw_raise": 0.0,           # chance to raise a bet with a real draw (flop/turn)...
    "draw_raise_agg": 0.0,       # ...when their postflop aggression rate is at least this
    "river_bluff_adapt": 0.0,    # chance to bluff air when their measured river fold rate pays
    "river_bluff_margin": 0.05,  # edge (in pots) the measured fold rate must clear
    "river_bluff_min_obs": 12,   # river bets they faced (per size) before trusting the rate
    # --- time and autopilot ----------------------------------------------
    "logic_share": 0.45,         # share of the 8 s bank our own code may spend
    "mc_max_samples": 1500,      # cap on Monte Carlo samples per decision
    "pot_exponent": 0.0,         # >0: spend samples in proportion to pot^this (bot/timebank.py)
    "autopilot_streak": 10,      # default actions in a row that mean "out of time"
    "autopilot_min_folds": 4,    # ...including this many folds to a bet
}


def make(overrides: dict | None = None) -> dict:
    params = dict(DEFAULTS)
    if overrides:
        unknown = set(overrides) - set(DEFAULTS)
        if unknown:
            raise KeyError(f"unknown params: {sorted(unknown)}")
        params.update(overrides)
    return params
