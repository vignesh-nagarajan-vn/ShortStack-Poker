"""Keep the statistics other bots see from us in an unremarkable band.

Adaptive bots classify their opponent from the same handful of numbers we
use (fold-to-bet, aggression, VPIP) and flip into an exploit mode once a
threshold is crossed: "folds over ~55% to bets -> bluff it", "raises over
~45% -> call it down". Measured from their side, our fold-to-bet sits at
0.45-0.51, right next to the bluff trigger.

So we track our own recency-weighted rates exactly as an opponent would
and nudge decisions only while we drift toward a trigger:

  * fold-to-bet above the cap while the opponent's aggression is rising
    -> call marginal bets a little wider (minimum defense), so "bluff it"
    stops paying
  * aggression above the cap  -> halve our bluffing, since we already
    look loose and bluffs would start getting called

Opponents that don't adapt (nits, honest bettors) are left alone: folding
to their bets is correct, and image doesn't matter to them.
"""

from __future__ import annotations

from bot.opponent import RAISES, Rate, Step
from game import Action, Street


class SelfImage:
    def __init__(self) -> None:
        self.fold_to_bet = Rate(prior=0.45, alpha=0.05)
        self.aggression = Rate(prior=0.38, alpha=0.05)

    def observe(self, steps: list[Step]) -> None:
        for i, s in enumerate(steps):
            if not s.is_me or s.street == Street.PREFLOP:
                continue
            if s.action != Action.FOLD:
                self.aggression.add(s.action in RAISES)
            prev = next((p for p in reversed(steps[:i]) if p.street == s.street), None)
            if prev is not None and not prev.is_me and prev.action in RAISES:
                self.fold_to_bet.add(s.action == Action.FOLD)

    def call_bonus(self, p: dict, profile: str, opp) -> float:
        """Extra equity we are willing to give up on a call to defend our image.

        Only paid while there is evidence the opponent is exploiting us:
        their recent aggression has risen clearly above their own average
        while we fold a lot. Against a static opponent this would just
        throw away equity (measured: -0.3 bb/deal when always on)."""
        if profile in ("nit", "honest"):
            return 0.0
        attacking = opp.recent("aggression") > opp.rate("aggression") + p["image_attack_gap"]
        if attacking and self.fold_to_bet.recent_value > p["image_ftb_cap"]:
            return p["image_call_bonus"]
        return 0.0

    def bluff_scale(self, p: dict) -> float:
        return 0.5 if self.aggression.recent_value > p["image_agg_cap"] else 1.0
