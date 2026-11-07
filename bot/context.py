"""Small helpers the strategy uses to read an Observation."""

from __future__ import annotations

from game import Action, Observation

RAISES = (Action.RAISE_HALF, Action.RAISE_POT)


class Ctx:
    """One decision: the observation plus convenient derived numbers."""

    def __init__(self, obs: Observation) -> None:
        self.obs = obs
        self.street = obs.street
        self.to_call = obs.to_call
        self.pot = obs.pot
        self.legal = obs.legal_actions
        self.can_raise = any(a in self.legal for a in RAISES)
        self.can_fold = Action.FOLD in self.legal
        # After the flop the button acts last, so it is "in position" for
        # the rest of the hand (preflop it acts first, but that is one street).
        self.in_position = obs.is_button
        self.opp_raises_this_street = sum(
            1 for a in obs.action_history
            if not a.is_me and a.street == obs.street and a.action in RAISES)
        self.opp_raises_total = sum(1 for a in obs.action_history
                                    if not a.is_me and a.action in RAISES)
        self.my_raises_total = sum(1 for a in obs.action_history
                                   if a.is_me and a.action in RAISES)

    @property
    def pot_odds(self) -> float:
        """Equity needed to break even on a call (ignoring future betting)."""
        if self.to_call <= 0:
            return 0.0
        call = min(self.to_call, self.obs.my_stack)
        return call / (self.pot + call)

    @property
    def effective_stack(self) -> int:
        return min(self.obs.my_stack, self.obs.opp_stack + max(0, -self.to_call))

    @property
    def spr(self) -> float:
        """Stack-to-pot ratio after calling."""
        pot = self.pot + min(self.to_call, self.obs.my_stack)
        return (self.obs.my_stack - min(self.to_call, self.obs.my_stack)) / max(1, pot)

    def raise_(self, size: Action = Action.RAISE_POT) -> Action:
        """Raise with the preferred size, or the other one, or call."""
        if size in self.legal:
            return size
        other = Action.RAISE_HALF if size == Action.RAISE_POT else Action.RAISE_POT
        return other if other in self.legal else Action.CHECK_CALL

    def fold(self) -> Action:
        """Fold when it costs something, otherwise check."""
        return Action.FOLD if self.can_fold else Action.CHECK_CALL

    def call(self) -> Action:
        return Action.CHECK_CALL
