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
