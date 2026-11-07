"""How the bot decides. Every decision reads one Ctx and returns an Action.

Preflop uses the precomputed percentile table (microseconds) for opening
and for answering limps; when facing a raise it estimates the opponent's
range from how many times they have raised and takes Monte Carlo equity
against that range.
"""

from __future__ import annotations

from game import Action, Street
from bot import preflop, ranges
from bot.context import Ctx


class Strategy:
    def __init__(self, brain) -> None:
        self.brain = brain
        self.p = brain.params

    # ------------------------------------------------------------------
    def decide(self, ctx: Ctx) -> Action:
        if ctx.street == Street.PREFLOP:
            return self.preflop(ctx)
        return self.postflop(ctx)

    def postflop(self, ctx: Ctx) -> Action:
        return ctx.call()

    # ------------------------------------------------------------------
    def range_floor(self, opp_raises: int) -> float:
        """Percentile floor of the opponent's preflop range after n raises."""
        if opp_raises <= 0:
            return 0.0
        if opp_raises == 1:
            return self.p["range_floor_1raise"]
        if opp_raises == 2:
            return self.p["range_floor_2raise"]
        return self.p["range_floor_3raise"]

    def equity_vs_range(self, ctx: Ctx, floor: float) -> float:
        hole = ctx.obs.hole_cards
        n = self.brain.samples(ctx)
        if n <= 0:
            # Out of time: approximate from the table (a tighter range costs equity).
            return preflop.equity(hole) - 0.12 * floor
        return self.brain.equity(hole, ctx.obs.board, n, ranges.preflop_floor(floor))

    def preflop(self, ctx: Ctx) -> Action:
        p = self.p
        pct = preflop.percentile(ctx.obs.hole_cards)
        opp_raises = ctx.opp_raises_this_street

        if opp_raises == 0:
            if ctx.obs.is_button and ctx.to_call > 0:
                # First action of the hand from the small blind.
                if pct >= p["sb_raise_pot_above"] and ctx.can_raise:
                    return ctx.raise_(Action.RAISE_POT)
                if pct >= p["sb_raise_half_above"] and ctx.can_raise:
                    return ctx.raise_(Action.RAISE_HALF)
                if pct < p["sb_fold_below"]:
                    return ctx.fold()
                return ctx.call()
            # Big blind after a limp: free check, raise good hands.
            if pct >= p["bb_raise_above"] and ctx.can_raise:
                return ctx.raise_(Action.RAISE_POT)
            return ctx.call()

        # Facing one or more raises.
        floor = self.range_floor(opp_raises)
        eq = self.equity_vs_range(ctx, floor)
        if eq >= p["pre_reraise_equity"] and ctx.can_raise:
            return ctx.raise_(Action.RAISE_POT)
        margin = p["pre_call_margin_ip"] if ctx.in_position else p["pre_call_margin_oop"]
        if eq >= ctx.pot_odds + margin:
            return ctx.call()
        return ctx.fold()
