"""Spot an opponent that has stopped thinking.

When a bot runs out of time bank, forfeits, or keeps crashing, the judge
plays for it: check when free, fold when facing a bet. Running out of time
is not a forfeit, so the match goes on, and that bot now gives up every
pot it is bet into. Many naive Monte Carlo bots will hit this late in a
half (omaha_score is slow), so we watch for it.

Detection: a run of at least STREAK opponent actions that all equal the
judge's default action, including at least MIN_FOLDS folds to a bet. Any
call or raise ends it immediately. While it lasts we raise every hand
(half-pot is enough: it folds to any bet), which wins the blinds every
hand at almost no risk.
"""

from __future__ import annotations

from game import Action

STREAK = 10
MIN_FOLDS = 4


class AutopilotDetector:
    def __init__(self) -> None:
        self.streak = 0
        self.folds = 0
        self.active = False
        self.triggers = 0

    def observe(self, steps, facing) -> None:
        """steps: opponent Steps of a finished hand, in order;
        facing: parallel list of bools (were they facing a bet?)."""
        for step, is_facing in zip(steps, facing):
            default = Action.FOLD if is_facing else Action.CHECK_CALL
            if step.action == default:
                self.streak += 1
                self.folds += step.action == Action.FOLD
            else:
                self.streak, self.folds = 0, 0
                self.active = False
        if not self.active and self.streak >= STREAK and self.folds >= MIN_FOLDS:
            self.active = True
            self.triggers += 1

    def woke_up(self) -> None:
        """The opponent called or raised during the current hand."""
        self.active = False
        self.streak, self.folds = 0, 0
