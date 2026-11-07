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
