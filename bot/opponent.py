"""What we learn about the opponent during one half.

The judge only shows us our own observations, so a hand's full action
sequence is rebuilt from the last action_history we saw, the action we
then chose, and the HandResult (a hand that ends without showdown after
our bet means the opponent folded; one we lose without showdown means we
folded).

Every frequency is shrunk toward a prior (a Bayesian average with
`prior_weight` pseudo-observations), so a handful of hands never swings
the strategy. Recency-weighted versions of the key rates are kept too, so
an opponent that changes gear mid-half is noticed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from game import Action, HandResult, Street

RAISES = (Action.RAISE_HALF, Action.RAISE_POT)

PRIORS = {
    "vpip": 0.75, "pfr": 0.35, "three_bet": 0.15,
    "aggression": 0.35,      # share of postflop actions that are bets/raises
    "fold_to_bet": 0.40,     # postflop folds when facing our bet
    "wtsd": 0.35,            # hands that reach showdown
}


@dataclass
class Rate:
    """A shrunk frequency plus an exponentially weighted recent version."""

    prior: float
    prior_weight: float = 12.0
    hits: float = 0.0
    total: float = 0.0
    recent: float = -1.0
    alpha: float = 0.06

    def add(self, hit: bool) -> None:
        self.hits += 1.0 if hit else 0.0
        self.total += 1.0
        x = 1.0 if hit else 0.0
        self.recent = self.value if self.recent < 0 else (1 - self.alpha) * self.recent + self.alpha * x

    @property
    def value(self) -> float:
        return (self.hits + self.prior * self.prior_weight) / (self.total + self.prior_weight)

    @property
    def recent_value(self) -> float:
        return self.value if self.recent < 0 else self.recent


@dataclass
class Step:
    """One action in a rebuilt hand."""

    street: Street
    is_me: bool
    action: Action


@dataclass
class OpponentModel:
    hands: int = 0
    rates: dict = field(default_factory=lambda: {k: Rate(v) for k, v in PRIORS.items()})
    showdowns: list = field(default_factory=list)      # (opp_hole, board, opp steps)
    last_steps: list = field(default_factory=list)
    # Share of our called river bets that won at showdown. Kept apart from
    # `rates` so profile classification and mode-shift checks ignore it.
    river_called_wins: Rate = field(default_factory=lambda: Rate(0.65))
    # How often they fold to our river bets, by size (a raise counts as no fold).
    river_fold_half: Rate = field(default_factory=lambda: Rate(0.30))
    river_fold_pot: Rate = field(default_factory=lambda: Rate(0.35))

    # ---- feeding ---------------------------------------------------------

    @staticmethod
    def rebuild(history, my_last: Action | None, result: HandResult) -> list[Step]:
        """Full action sequence of a finished hand, as far as we can know it."""
        steps = [Step(a.street, a.is_me, a.action) for a in history]
        if my_last is not None:
            street = history[-1].street if history else Street.PREFLOP
            # Our last action may have been on a later street than the history's
            # last entry; that detail does not matter for the statistics below.
            steps.append(Step(street, True, my_last))
        street = steps[-1].street if steps else Street.PREFLOP
        if not result.went_to_showdown:
            if result.winner == "me" and (not steps or steps[-1].action != Action.FOLD):
                steps.append(Step(street, False, Action.FOLD))
        elif steps and steps[-1].is_me and steps[-1].action in RAISES:
            steps.append(Step(street, False, Action.CHECK_CALL))   # they called our last bet
        return steps

    def observe_hand(self, steps: list[Step], result: HandResult) -> None:
        self.hands += 1
        self.last_steps = steps
        r = self.rates
        opp_pre = [s for s in steps if not s.is_me and s.street == Street.PREFLOP]
        if opp_pre:
            # Voluntary: any raise, a call of our raise, or a small-blind limp
            # (the very first action of the hand). A big-blind check is not.
            r["vpip"].add(any(
                s.action in RAISES
                or (s.action == Action.CHECK_CALL and (s is steps[0] or self._facing_raise(steps, s)))
                for s in opp_pre))
            r["pfr"].add(any(s.action in RAISES for s in opp_pre))
            faced = [s for s in opp_pre if self._facing_raise(steps, s)]
            if faced:
                r["three_bet"].add(any(s.action in RAISES for s in faced))
        for s in steps:
            if s.is_me or s.street == Street.PREFLOP:
                continue
            if s.action != Action.FOLD:
                r["aggression"].add(s.action in RAISES)
            if self._facing_raise(steps, s):
                r["fold_to_bet"].add(s.action == Action.FOLD)
        if any(s.street != Street.PREFLOP for s in steps) or result.went_to_showdown:
            r["wtsd"].add(result.went_to_showdown)
        self._river_folds(steps)
        if result.went_to_showdown and self._called_our_river_bet(steps):
            self.river_called_wins.add(result.winner == "me")
        if result.went_to_showdown and result.opp_hole:
            opp_steps = [s for s in steps if not s.is_me]
            self.showdowns.append((tuple(result.opp_hole), tuple(result.board), opp_steps))

    @classmethod
    def opponent_facing(cls, steps: list[Step]) -> tuple[list[Step], list[bool]]:
        """The opponent's steps and whether each one faced a bet. The small
        blind's first action faces the big blind, so it counts as facing."""
        opp = [s for s in steps if not s.is_me]
        facing = [cls._facing_raise(steps, s) or (s is steps[0] and s.street == Street.PREFLOP)
                  for s in opp]
        return opp, facing

    @staticmethod
    def _facing_raise(steps: list[Step], step: Step) -> bool:
        """Was the opponent facing a bet/raise from us when taking `step`?"""
        idx = next(i for i, s in enumerate(steps) if s is step)
        for prev in reversed(steps[:idx]):
            if prev.street != step.street:
                break
            if prev.is_me:
                return prev.action in RAISES
        return False

    def _river_folds(self, steps: list[Step]) -> None:
        river = [s for s in steps if s.street == Street.RIVER]
        for mine, theirs in zip(river, river[1:]):
            if mine.is_me and mine.action in RAISES and not theirs.is_me:
                rate = self.river_fold_half if mine.action == Action.RAISE_HALF else self.river_fold_pot
                rate.add(theirs.action == Action.FOLD)

    @staticmethod
    def _called_our_river_bet(steps: list[Step]) -> bool:
        """Did the hand end with the opponent calling our river bet/raise?"""
        river = [s for s in steps if s.street == Street.RIVER]
        return (len(river) >= 2 and river[-2].is_me and river[-2].action in RAISES
                and not river[-1].is_me and river[-1].action == Action.CHECK_CALL)

    # ---- reading ---------------------------------------------------------

    def rate(self, name: str) -> float:
        return self.rates[name].value

    def recent(self, name: str) -> float:
        return self.rates[name].recent_value

    def summary(self) -> str:
        return " ".join(f"{k}={v.value:.2f}" for k, v in self.rates.items()) + f" hands={self.hands}"
