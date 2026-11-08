"""Opponent pool: the kinds of bots we expect other teams to submit.

Simple archetypes cover starter-code and hand-written bots that need to
be beaten by a wide margin for points and the bb/deal tiebreaker.
"""

from __future__ import annotations

import random

from evaluator import FLUSH, omaha_score
from game import Action, Street
from sim.heuristics import preflop_score
from sim.players import Player

RAISES = (Action.RAISE_HALF, Action.RAISE_POT)


def _raise(obs, prefer: Action = Action.RAISE_POT) -> Action:
    if prefer in obs.legal_actions:
        return prefer
    other = Action.RAISE_HALF if prefer == Action.RAISE_POT else Action.RAISE_POT
    return other if other in obs.legal_actions else Action.CHECK_CALL


def _fold_or_check(obs) -> Action:
    return Action.FOLD if Action.FOLD in obs.legal_actions else Action.CHECK_CALL


class CheckFold(Player):
    """The untouched starter template: check when free, otherwise fold."""

    def act(self, obs):
        return Action.CHECK_CALL if obs.to_call == 0 else Action.FOLD


class GuideExample(Player):
    """The example strategy printed in the participant guide (section 4.1)."""

    def act(self, obs):
        if obs.street != Street.RIVER:
            if obs.to_call <= obs.big_blind:
                return Action.CHECK_CALL
            return _fold_or_check(obs)
        score = omaha_score(obs.hole_cards, obs.board)
        if score >= (FLUSH << 20) and Action.RAISE_POT in obs.legal_actions:
            return Action.RAISE_POT
        return Action.CHECK_CALL


class Nit(Player):
    """Plays only strong starting hands; bets made hands on the river, folds to pressure otherwise."""

    def __init__(self, config, threshold: float = 0.55):
        super().__init__(config)
        self.threshold = threshold

    def act(self, obs):
        strength = preflop_score(obs.hole_cards)
        if obs.street == Street.PREFLOP:
            if strength >= self.threshold + 0.1:
                return _raise(obs)
            if strength >= self.threshold:
                return Action.CHECK_CALL
            return _fold_or_check(obs)
        if obs.street == Street.RIVER:
            cat = omaha_score(obs.hole_cards, obs.board) >> 20
            if cat >= 4:
                return _raise(obs)
            if cat >= 2 and obs.to_call <= obs.pot // 2:
                return Action.CHECK_CALL
            return _fold_or_check(obs)
        if obs.to_call == 0:
            return Action.CHECK_CALL
        return Action.CHECK_CALL if strength >= self.threshold + 0.1 else _fold_or_check(obs)


class Maniac(Player):
    """Raises most of the time, never folds."""

    def __init__(self, config, raise_rate: float = 0.7, seed: int = 7):
        super().__init__(config)
        self.raise_rate = raise_rate
        self.rng = random.Random(seed)

    def act(self, obs):
        raises = [a for a in obs.legal_actions if a in RAISES]
        if raises and self.rng.random() < self.raise_rate:
            return self.rng.choice(raises)
        return Action.CHECK_CALL


class McThreshold(Player):
    """The most likely competitor design: Monte Carlo equity against one
    random hand, compared with fixed thresholds and the pot odds.

    raise_thr  equity needed to raise (pot-size when facing a bet)
    bet_thr    equity needed to bet when checked to
    margin     extra equity demanded over the pot odds before calling
    bluff      chance to bet/raise as a bluff with weak equity
    sims       Monte Carlo samples per decision (big values drain the time bank)
    """

    def __init__(self, config, sims: int = 10, raise_thr: float = 0.65, bet_thr: float = 0.55,
                 margin: float = 0.0, bluff: float = 0.0, half_size: bool = False, seed: int = 11):
        super().__init__(config)
        self.sims, self.raise_thr, self.bet_thr = sims, raise_thr, bet_thr
        self.margin, self.bluff, self.half_size = margin, bluff, half_size
        self.rng = random.Random(seed)

    def equity(self, obs) -> float:
        from sim.heuristics import mc_equity
        return mc_equity(obs.hole_cards, obs.board, self.sims, self.rng)

    def act(self, obs):
        from sim.heuristics import pot_odds
        eq = self.equity(obs)
        size = Action.RAISE_HALF if self.half_size else Action.RAISE_POT
        can_raise = any(a in obs.legal_actions for a in RAISES)
        if eq >= self.raise_thr and can_raise:
            return _raise(obs, size)
        if obs.to_call == 0:
            if can_raise and (eq >= self.bet_thr or self.rng.random() < self.bluff):
                return _raise(obs, size)
            return Action.CHECK_CALL
        if eq >= pot_odds(obs) + self.margin:
            return Action.CHECK_CALL
        return _fold_or_check(obs)


class AdaptiveExploiter(McThreshold):
    """What a more ambitious team builds: the MC threshold bot plus an
    opponent model (VPIP, PFR, aggression, fold-to-bet) that classifies us
    after a warm-up and switches into a matching exploit mode:

      folds a lot to bets  -> bluff much more
      raises a lot         -> call down wider, stop bluffing
      plays few hands      -> steal preflop with any hand
      never folds          -> value bet thinner, never bluff
    """

    WARMUP = 40

    def __init__(self, config, **kwargs):
        super().__init__(config, **kwargs)
        self.base = (self.raise_thr, self.bet_thr, self.margin, self.bluff)
        self.hands = 0
        self.vpip = 0
        self.opp_raises = 0
        self.opp_actions = 0
        self.faced_bets = 0
        self.folds_to_bet = 0
        self.mode = "default"
        self._last_history = ()
        self._we_bet_last = False

    def act(self, obs):
        self._last_history = obs.action_history
        self._we_bet_last = False
        if self.mode == "steal" and obs.street == Street.PREFLOP and obs.is_button:
            if any(a in obs.legal_actions for a in RAISES):
                self._we_bet_last = True
                return _raise(obs, Action.RAISE_HALF)
        action = super().act(obs)
        self._we_bet_last = action in RAISES
        return action

    def hand_end(self, result):
        self.hands += 1
        opp = [a for a in self._last_history if not a.is_me]
        if any(a.street == Street.PREFLOP and a.action != Action.FOLD for a in opp):
            self.vpip += 1
        self.opp_actions += len(opp)
        self.opp_raises += sum(1 for a in opp if a.action in RAISES)
        # Each of our bets/raises the opponent answered is a "faced bet".
        hist = list(self._last_history)
        for i, a in enumerate(hist):
            if a.is_me and a.action in RAISES and i + 1 < len(hist) and not hist[i + 1].is_me:
                self.faced_bets += 1
        if self._we_bet_last and not result.went_to_showdown and result.winner == "me":
            self.faced_bets += 1
            self.folds_to_bet += 1
        if self.hands >= self.WARMUP and self.hands % 10 == 0:
            self._reclassify()

    def _reclassify(self):
        raise_thr, bet_thr, margin, bluff = self.base
        vpip = self.vpip / self.hands
        aggr = self.opp_raises / max(1, self.opp_actions)
        ftb = self.folds_to_bet / max(1, self.faced_bets)
        if aggr > 0.45:
            self.mode, margin, bluff = "call_down", margin - 0.08, 0.0
        elif ftb > 0.55:
            self.mode, bluff = "bluff", 0.45
        elif vpip < 0.45:
            self.mode = "steal"
        elif ftb < 0.2:
            self.mode, bet_thr, bluff = "value", bet_thr - 0.05, 0.0
        else:
            self.mode = "default"
        self.raise_thr, self.bet_thr, self.margin, self.bluff = raise_thr, bet_thr, margin, bluff


class WeakTight(Player):
    """Calls or checks with any pair or better made hand by the river, folds to bets before that
    unless the preflop score is decent. Never raises: a passive, easily bullied bot."""

    def act(self, obs):
        if obs.to_call == 0:
            return Action.CHECK_CALL
        if obs.street == Street.RIVER:
            cat = omaha_score(obs.hole_cards, obs.board) >> 20
            return Action.CHECK_CALL if cat >= 2 else _fold_or_check(obs)
        if preflop_score(obs.hole_cards) >= 0.5 and obs.to_call <= obs.pot:
            return Action.CHECK_CALL
        return _fold_or_check(obs)


class BrownClone(Player):
    """In-process clone of BrownBallers (github.com/snr2753423/heads-up-bot,
    strategy/policy.py + strategy/opponent.py, Nov 2026), a rival we beat
    10/10 on the real judge. It is the "MC equity vs one random hand"
    family done carefully:

      * preflop: a 40-sample equity-vs-random table (noisy, so we add the
        same size of noise to our exact table)
      * postflop: omaha_score Monte Carlo vs ONE random hand, 48 samples on
        the flop, 32 on the turn, 36 on the river (slow: drains the bank)
      * fixed thresholds (T below) shifted by a live model of our fold and
        raise rates and of the hands we show down

    Its bundled profile library (identify.py) is left out: it only matches
    starter/baseline bots, never us.
    """

    T = {"call_margin": 0.04, "facing_pot": 0.78, "facing_half": 0.68, "bet_pot": 0.72,
         "bet_half": 0.58, "button_bet_discount": 0.04, "preflop_raise_penalty": 0.06,
         "allin_extra": 0.05, "open_raise": 0.53, "open_call": 0.42, "bb_option_raise": 0.58,
         "min_value_bet": 0.55}
    SAMPLES = {3: 48, 4: 32, 5: 36}

    def __init__(self, config, seed: int = 5, preflop_noise: float = 0.075, samples_scale: float = 1.0):
        super().__init__(config)
        self.rng = random.Random(seed)
        self.noise = preflop_noise
        self.samples_scale = samples_scale
        self.stats = {"pre": dict(fold=0, cont=0, raise_=0, non=0),
                      "post": dict(fold=0, cont=0, raise_=0, non=0)}
        self.show = dict(n=0, weak=0, strong=0)
        self.cursor = (None, 0)
        self.we_bet = False
        self.last_street = None
        self.cache = None

    # --- equity -----------------------------------------------------------
    def equity(self, obs) -> float:
        key = (obs.hand_index, int(obs.street), tuple(obs.board))
        if self.cache and self.cache[0] == key:
            return self.cache[1]
        if len(obs.board) < 3:
            from bot import preflop
            hole = tuple(sorted(obs.hole_cards))
            jitter = random.Random(sum(c << (6 * i) for i, c in enumerate(hole))).gauss(0.0, self.noise)
            eq = min(0.95, max(0.05, preflop.equity(hole) + jitter))
        else:
            from sim.heuristics import mc_equity
            n = max(4, int(self.SAMPLES[len(obs.board)] * self.samples_scale))
            eq = mc_equity(obs.hole_cards, obs.board, n, self.rng)
        self.cache = (key, eq)
        return eq

    # --- opponent model (strategy/opponent.py) ---------------------------
    def _observe(self, obs) -> None:
        hand, start = self.cursor
        if hand != obs.hand_index:
            start = 0
        for a in obs.action_history[start:]:
            if a.is_me:
                continue
            st = self.stats["pre" if a.street == Street.PREFLOP else "post"]
            if a.action == Action.FOLD:
                st["fold"] += 1
                st["non"] += 1
            elif a.action in RAISES:
                st["raise_"] += 1
                st["cont"] += 1
            elif a.amount > 0:
                st["cont"] += 1
                st["non"] += 1
            else:
                st["non"] += 1
        self.cursor = (obs.hand_index, len(obs.action_history))
        self.last_street = obs.street

    def _adjust(self, to_call: int, is_button: bool) -> dict:
        post, pre = self.stats["post"], self.stats["pre"]
        use = post if post["fold"] + post["cont"] >= 25 else (
            pre if pre["fold"] + pre["cont"] >= 25 else post)
        fold_obs = use["fold"] + use["cont"]
        raise_obs = use["raise_"] + use["non"]
        fold_rate = (8 + use["fold"]) / (20 + fold_obs)
        raise_rate = (6 + use["raise_"]) / (20 + raise_obs)
        n, weak, strong = self.show["n"], self.show["weak"], self.show["strong"]
        weak_rate = (3 + weak) / (8 + weak + strong)
        strong_rate = (5 + strong) / (8 + weak + strong)
        bet = call = value = 0.0
        station = False
        if fold_obs >= 25 and fold_rate > 0.55 and to_call == 0:
            bet -= 0.08 + (0.04 if is_button else 0.0)
        if (fold_obs >= 25 and fold_rate < 0.25) or (n >= 15 and weak_rate > 0.55):
            bet += 0.08
            value -= 0.04
            station = True
        if raise_obs >= 25 and raise_rate > 0.55 and n >= 15:
            if strong_rate > 0.5:
                call += 0.05
            if weak_rate > 0.5:
                call -= 0.05
        return dict(bet=bet, call=call, value=value, station=station)

    # --- policy (strategy/policy.py) -------------------------------------
    @staticmethod
    def _clamp(x: float) -> float:
        return max(0.30, min(0.90, x))

    def _raise(self, obs, eq: float, pot_at: float, half_at: float):
        for action, need in ((Action.RAISE_POT, pot_at), (Action.RAISE_HALF, half_at)):
            if action not in obs.legal_actions:
                continue
            total = obs.raise_to.get(action)
            extra = self.T["allin_extra"] if total is not None and total >= obs.my_bet + obs.my_stack else 0.0
            if eq >= need + extra:
                return action
        return None

    def _choose(self, obs) -> Action:
        T = self.T
        eq = self.equity(obs)
        s = self._adjust(obs.to_call, obs.is_button)
        postflop = obs.street != Street.PREFLOP
        pos = T["button_bet_discount"] if obs.is_button and postflop else 0.0
        bet_pot = self._clamp(T["bet_pot"] + s["bet"] + s["value"] - pos)
        bet_half = min(bet_pot, self._clamp(T["bet_half"] + s["bet"] - pos))
        facing_pot = self._clamp(T["facing_pot"] + s["value"])
        facing_half = min(facing_pot, self._clamp(T["facing_half"] + s["bet"]))
        if obs.street == Street.PREFLOP and obs.to_call <= obs.big_blind:
            if obs.is_button:
                open_raise = self._clamp(T["open_raise"] + s["bet"])
                if eq >= open_raise:
                    r = self._raise(obs, eq, open_raise, open_raise)
                    if r is not None:
                        return r
                if eq >= T["open_call"] or Action.FOLD not in obs.legal_actions:
                    return Action.CHECK_CALL
                return Action.FOLD
            option = self._clamp(T["bb_option_raise"] + s["bet"] + s["value"])
            if eq >= option:
                r = self._raise(obs, eq, option, option)
                if r is not None:
                    return r
            return Action.CHECK_CALL
        if obs.to_call <= 0:
            if s["station"] and eq < T["min_value_bet"]:
                return Action.CHECK_CALL
            r = self._raise(obs, eq, bet_pot, bet_half)
            return r if r is not None else Action.CHECK_CALL
        penalty = T["preflop_raise_penalty"] if obs.street == Street.PREFLOP else 0.0
        price = obs.to_call / (obs.pot + obs.to_call)
        need_call = price + T["call_margin"] + s["call"] + penalty
        r = self._raise(obs, eq, facing_pot + penalty, facing_half + penalty)
        if r is not None:
            return r
        if eq >= need_call:
            return Action.CHECK_CALL
        return _fold_or_check(obs)

    def act(self, obs):
        self._observe(obs)
        action = self._choose(obs)
        if action not in obs.legal_actions:
            action = Action.CHECK_CALL
        self.we_bet = action in RAISES
        return action

    def hand_end(self, result):
        from evaluator import STRAIGHT, TWO_PAIR, category_of
        if not result.went_to_showdown and result.winner == "me" and self.we_bet and self.last_street is not None:
            st = self.stats["pre" if self.last_street == Street.PREFLOP else "post"]
            st["fold"] += 1
            st["non"] += 1
        self.we_bet = False
        if not result.went_to_showdown or result.opp_hole is None or len(result.board) != 5:
            return
        cat = category_of(omaha_score(result.opp_hole, result.board))
        self.show["n"] += 1
        if cat >= STRAIGHT and result.winner == "opp":
            self.show["strong"] += 1
        elif cat <= TWO_PAIR or (result.winner == "me" and result.pot >= 20):
            self.show["weak"] += 1


class RangeBot(Player):
    """A strong, fast, range-aware bot that is NOT built on our strategy:
    equity from our vectorised engine against a range implied by the
    opponent's bets this hand, value bets plus bluffs from the bottom of its
    range, and calls priced off pot odds. Stands in for the best teams in
    the field, which will also have fast evaluators."""

    def __init__(self, config, samples: int = 250, bet_eq: float = 0.62, raise_eq: float = 0.72,
                 bluff: float = 0.33, call_margin: float = 0.02, agg_level: float = 0.45,
                 seed: int = 23):
        super().__init__(config)
        from bot.equity import EquityEngine
        self.engine = EquityEngine(seed=seed)
        self.rng = random.Random(seed)
        self.samples, self.bet_eq, self.raise_eq = samples, bet_eq, raise_eq
        self.bluff, self.call_margin, self.agg_level = bluff, call_margin, agg_level

    def act(self, obs):
        from bot import preflop, ranges
        can_raise = any(a in obs.legal_actions for a in RAISES)
        opp_raises = sum(1 for a in obs.action_history if not a.is_me and a.action in RAISES
                         and a.street == obs.street)
        if obs.street == Street.PREFLOP:
            pct = preflop.percentile(obs.hole_cards)
            if opp_raises == 0:
                if pct >= 0.55 and can_raise:
                    return _raise(obs, Action.RAISE_POT if pct > 0.8 else Action.RAISE_HALF)
                if obs.to_call > 0 and pct < 0.08:
                    return _fold_or_check(obs)
                return Action.CHECK_CALL
            floor = min(0.85, 0.35 + 0.2 * opp_raises)
            eq = self.engine.equity(obs.hole_cards, [], self.samples, ranges.preflop_floor(floor))
            if eq >= 0.58 and can_raise:
                return _raise(obs, Action.RAISE_POT)
            odds = obs.to_call / (obs.pot + obs.to_call)
            return Action.CHECK_CALL if eq >= odds + 0.02 else _fold_or_check(obs)
        level = 0.0 if opp_raises == 0 else min(0.85, self.agg_level + 0.18 * (opp_raises - 1))
        weight = ranges.postflop_weight(obs.board, 0.0, level)
        eq = self.engine.equity(obs.hole_cards, obs.board, self.samples, weight)
        size = Action.RAISE_POT if eq > 0.8 else Action.RAISE_HALF
        if obs.to_call == 0:
            if can_raise and eq >= self.bet_eq:
                return _raise(obs, size)
            if can_raise and eq < 0.3 and self.rng.random() < self.bluff:
                return _raise(obs, Action.RAISE_HALF)
            return Action.CHECK_CALL
        if can_raise and eq >= self.raise_eq:
            return _raise(obs, size)
        odds = obs.to_call / (obs.pot + obs.to_call)
        return Action.CHECK_CALL if eq >= odds + self.call_margin else _fold_or_check(obs)


class Barreler(McThreshold):
    """Bets whenever checked to with probability `cbet`, whatever it holds,
    on every street: a bluff-heavy bot that punishes a high fold-to-bet.
    Facing bets it plays like McThreshold."""

    def __init__(self, config, cbet: float = 0.7, **kwargs):
        super().__init__(config, **kwargs)
        self.cbet = cbet

    def act(self, obs):
        if obs.street != Street.PREFLOP and obs.to_call == 0 and any(a in obs.legal_actions for a in RAISES):
            if self.rng.random() < self.cbet:
                return _raise(obs, Action.RAISE_HALF if self.half_size else Action.RAISE_POT)
        return super().act(obs)
