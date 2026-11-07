"""How the bot decides. Every decision reads one Ctx and returns an Action.

Preflop uses the precomputed percentile table (microseconds) for opening
and for answering limps; when facing a raise it estimates the opponent's
range from how many times they have raised and takes Monte Carlo equity
against that range.
"""

from __future__ import annotations

from game import Action, Street
from bot import preflop, ranges
from bot.draws import has_draw
from bot.context import RAISES, Ctx


class Strategy:
    def __init__(self, brain) -> None:
        self.brain = brain
        self.p = brain.params

    # ------------------------------------------------------------------
    def decide(self, ctx: Ctx) -> Action:
        if ctx.street == Street.PREFLOP:
            return self.preflop(ctx)
        return self.postflop(ctx)

    # ------------------------------------------------------------------
    def opponent_preflop_floor(self, ctx: Ctx) -> float:
        """Percentile floor implied by the opponent's preflop line."""
        hist = ctx.obs.action_history
        opp_pre = [a for a in hist if not a.is_me and a.street == Street.PREFLOP]
        raises = sum(1 for a in opp_pre if a.action in RAISES)
        if raises:
            return self.range_floor(raises)
        we_raised = any(a.is_me and a.street == Street.PREFLOP and a.action in RAISES for a in hist)
        if we_raised and opp_pre:
            return self.p["range_floor_call"]
        return 0.0

    def opponent_aggression(self, ctx: Ctx) -> float:
        """How strong the opponent's postflop betting says their made hand is."""
        p = self.p
        k = ctx.opp_raises_this_street
        level = 0.0 if k == 0 else p["agg_bet"] if k == 1 else p["agg_raise"] if k == 2 else p["agg_reraise"]
        earlier = {a.street for a in ctx.obs.action_history
                   if not a.is_me and a.action in RAISES and Street.PREFLOP < a.street < ctx.street}
        if earlier:
            level = max(level, p["agg_bet"]) + p["agg_prev_street"] * len(earlier)
        return min(level, 0.9)

    def postflop_equity(self, ctx: Ctx) -> float:
        n = self.brain.samples(ctx)
        if n <= 0:
            return -1.0
        weight = ranges.postflop_weight(ctx.obs.board, self.opponent_preflop_floor(ctx),
                                        self.opponent_aggression(ctx),
                                        draw_credit=self.p["draw_credit"])
        return self.brain.equity(ctx.obs.hole_cards, ctx.obs.board, n, weight)

    def postflop(self, ctx: Ctx) -> Action:
        p = self.p
        eq = self.postflop_equity(ctx)
        if eq < 0:                      # out of thinking time: free checks, cheap calls only
            return ctx.call() if ctx.to_call == 0 or ctx.pot_odds < 0.2 else ctx.fold()
        size = Action.RAISE_POT if eq >= p["post_pot_size_eq"] else Action.RAISE_HALF
        if ctx.to_call == 0:
            bet_eq = p["post_bet_eq_river"] if ctx.street == Street.RIVER else p["post_bet_eq"]
            if eq >= bet_eq and ctx.can_raise:
                return ctx.raise_(size)
            if ctx.can_raise and self.should_bluff(ctx, eq):
                return ctx.raise_(Action.RAISE_HALF)
            return ctx.call()
        if eq >= p["post_raise_eq"] and ctx.can_raise:
            return ctx.raise_(size)
        if eq >= ctx.pot_odds + p["post_call_margin"]:
            return ctx.call()
        return ctx.fold()

    def should_bluff(self, ctx: Ctx, eq: float) -> bool:
        """Semi-bluff real draws before the river; rarely bluff air on the
        river from position. Opponent modeling scales these later."""
        p, rng = self.p, self.brain.rng
        if ctx.street != Street.RIVER:
            if eq >= p["semi_bluff_min_eq"] and has_draw(ctx.obs.hole_cards, ctx.obs.board):
                return rng.random() < p["semi_bluff_freq"]
            return False
        if ctx.in_position and eq <= p["river_bluff_max_eq"]:
            return rng.random() < p["river_bluff_freq"]
        return False

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
