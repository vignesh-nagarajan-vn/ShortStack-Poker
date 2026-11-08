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
from bot.equity import add_parts, parts_equity, parts_stderr

ADAPT_MIN = 60     # smallest first-stage sample when sampling in two stages


class Strategy:
    def __init__(self, brain) -> None:
        self.brain = brain
        self.p = brain.params

    # ------------------------------------------------------------------
    def decide(self, ctx: Ctx) -> Action:
        auto = self.brain.autopilot
        if auto.active:
            if any(not a.is_me and (a.action in RAISES or (a.action == Action.CHECK_CALL and a.amount > 0))
                   for a in ctx.obs.action_history):
                auto.woke_up()          # they called or raised: back to normal play
            elif ctx.can_raise and self.p["autopilot_steal"]:
                return ctx.raise_(Action.RAISE_HALF)
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
            return self.call_floor()
        return 0.0

    def opponent_aggression(self, ctx: Ctx) -> float:
        """How strong the opponent's postflop betting says their made hand is.

        A bettor that bets X% of the time is betting roughly its top X%, so
        the level moves from the prior toward 1 - aggression rate, then
        toward what their showdown hands actually were."""
        p = self.p
        k = ctx.opp_raises_this_street
        agg = self.brain.opponent.rates["aggression"]
        bet = p["agg_bet"]
        if p["learn_postflop"]:
            freq_level = min(0.85, max(0.10, 1.0 - agg.value))
            bet = self.brain.showdowns.bet_level(self._blend(p["agg_bet"], freq_level, agg.total, 60.0),
                                                 ctx.street if p["street_levels"] else None)
        if k == 0:
            level = 0.0
        elif not p["learn_postflop"]:
            level = p["agg_bet"] if k == 1 else p["agg_raise"] if k == 2 else p["agg_reraise"]
        elif k == 1:
            level = bet
        elif k == 2:
            level = self.brain.showdowns.raise_level(max(p["agg_raise"], bet + 0.15))
        else:
            level = max(p["agg_reraise"], bet + 0.3)
        earlier = {a.street for a in ctx.obs.action_history
                   if not a.is_me and a.action in RAISES and Street.PREFLOP < a.street < ctx.street}
        if earlier:
            if p["agg_prev_adapt"]:
                # A bot that bets almost every street says little by betting
                # again. Selective bettors (aggression <= 50%) keep the fixed
                # floor and step; above that both fade toward the learned bet
                # level as their aggression rate approaches 1.
                scale = min(1.0, max(0.0, 2.0 * (1.0 - agg.value)))
                floor = scale * p["agg_bet"] + (1.0 - scale) * min(bet, p["agg_bet"])
                level = max(level, floor) + p["agg_prev_street"] * len(earlier) * scale
            else:
                level = max(level, p["agg_bet"]) + p["agg_prev_street"] * len(earlier)
        return min(level, 0.9)

    def estimate(self, ctx: Ctx, weight, marks) -> float:
        """Equity for this decision, or -1 when out of thinking time.

        With `adaptive_samples` on, a first stage of `adaptive_first` of the
        samples is taken; the rest are only spent when that estimate lies
        within `adaptive_z` standard errors of a threshold (`marks`) the
        decision depends on. Clear spots then cost a fraction of the time,
        and the time bank hands the savings to later decisions."""
        n = self.brain.samples(ctx)
        if n <= 0:
            return -1.0
        hole, board, p = ctx.obs.hole_cards, ctx.obs.board, self.p
        if not p["adaptive_samples"] or n < 2 * ADAPT_MIN:
            return self.brain.equity(hole, board, n, weight)
        first = max(ADAPT_MIN, int(n * p["adaptive_first"]))
        parts = self.brain.equity_parts(hole, board, first, weight)
        eq, se = parts_equity(parts), parts_stderr(parts)
        if marks and min(abs(eq - m) for m in marks) < p["adaptive_z"] * se:
            parts = add_parts(parts, self.brain.equity_parts(hole, board, n - first, weight))
        return parts_equity(parts)

    def postflop_equity(self, ctx: Ctx, marks=()) -> float:
        weight = ranges.postflop_weight(ctx.obs.board, self.opponent_preflop_floor(ctx),
                                        self.opponent_aggression(ctx),
                                        draw_credit=self.p["draw_credit"])
        return self.estimate(ctx, weight, marks)

    def postflop_marks(self, ctx: Ctx) -> list:
        """The equity thresholds postflop() compares against (no side effects)."""
        p = self.p
        if ctx.to_call > 0 and ctx.committed_after_call(p["commit_ratio"]):
            return [p["commit_shove_eq"], ctx.allin_odds]
        if ctx.to_call == 0:
            if ctx.street == Street.RIVER:
                bet_eq = p["post_bet_eq_river"] - self.thin_river_shift()
            else:
                bet_eq = p["post_bet_eq"]
            if ctx.spr < p["low_spr"]:
                bet_eq = min(bet_eq, p["low_spr_bet_eq"])
            return [bet_eq, p["post_pot_size_eq"]]
        raise_eq = p["post_raise_eq"]
        if ctx.street == Street.RIVER and p["thin_river_raise"]:
            raise_eq -= self.thin_river_shift()
        bonus = self.brain.image.call_bonus(p, self.brain.profiler.profile, self.brain.opponent)
        return [raise_eq, p["post_pot_size_eq"], self.call_odds(ctx) + p["post_call_margin"] - bonus]

    def postflop(self, ctx: Ctx) -> Action:
        p = self.p
        eq = self.postflop_equity(ctx, self.postflop_marks(ctx) if p["adaptive_samples"] else ())
        if eq < 0:                      # out of thinking time: free checks, cheap calls only
            return ctx.call() if ctx.to_call == 0 or ctx.pot_odds < 0.2 else ctx.fold()
        size = Action.RAISE_POT if eq >= p["post_pot_size_eq"] else Action.RAISE_HALF
        if ctx.to_call > 0 and ctx.committed_after_call(p["commit_ratio"]):
            return self.committed(ctx, eq)
        if ctx.to_call == 0:
            if ctx.street == Street.RIVER:
                bet_eq = p["post_bet_eq_river"] - self.thin_river_shift()
            else:
                bet_eq = p["post_bet_eq"]
            if ctx.spr < p["low_spr"]:
                bet_eq = min(bet_eq, p["low_spr_bet_eq"])
                size = Action.RAISE_POT
            elif ctx.street == Street.RIVER and ctx.can_raise:
                verdict = self.river_value(ctx)
                if verdict is not None:          # None: not enough evidence, use the default rule
                    if verdict:
                        return ctx.raise_(Action.RAISE_POT if verdict == 2 else Action.RAISE_HALF)
                    bet_eq = 2.0                 # their calling range beats us: no value bet
            if eq >= bet_eq and ctx.can_raise:
                return ctx.raise_(size)
            if ctx.can_raise and ctx.street == Street.RIVER:
                bluff = self.river_bluff(ctx, eq)
                if bluff is not None:
                    return ctx.raise_(bluff)
            if ctx.can_raise and self.should_bluff(ctx, eq):
                return ctx.raise_(Action.RAISE_HALF)
            return ctx.call()
        raise_eq = p["post_raise_eq"]
        if ctx.street == Street.RIVER and p["thin_river_raise"]:
            raise_eq -= self.thin_river_shift()
        if eq >= raise_eq and ctx.can_raise:
            return ctx.raise_(size)
        if ctx.can_raise and self.draw_raise(ctx, eq):
            return ctx.raise_(Action.RAISE_POT)
        bonus = self.brain.image.call_bonus(p, self.brain.profiler.profile, self.brain.opponent)
        if eq >= self.call_odds(ctx) + p["post_call_margin"] - bonus:
            return ctx.call()
        return ctx.fold()

    def thin_river_shift(self) -> float:
        """Lower the river value-bet bar when the opponent's river calls keep
        losing: they call with hands worse than we assume, so medium hands
        are value too. Self-correcting: thinner bets lose more often, which
        pulls the win rate (and the shift) back down."""
        p = self.p
        rate = self.brain.opponent.river_called_wins
        if rate.total < p["thin_river_min"]:
            return 0.0
        span = max(1e-6, p["thin_river_full"] - p["thin_river_from"])
        scale = min(1.0, max(0.0, (rate.value - p["thin_river_from"]) / span))
        return p["thin_river_shift"] * scale

    def river_value(self, ctx: Ctx):
        """Value-bet the river against the hands that actually call us.

        Showdowns of called river bets give the bottom of their calling
        range; a value bet pays when we beat that range more often than
        `river_value_need`. Returns None (no opinion), 0 (check), 1 (bet
        half pot) or 2 (bet pot)."""
        p, sd = self.p, self.brain.showdowns
        if not p["river_value_range"] or len(sd.river_call_strengths) < p["river_call_min"]:
            return None
        n = self.brain.samples(ctx)
        if n <= 0:
            return None
        floor = sd.river_call_floor(prior=p["river_call_prior"])
        weight = ranges.postflop_weight(ctx.obs.board, self.opponent_preflop_floor(ctx), floor,
                                        softness=0.08)
        eq_called = self.brain.equity(ctx.obs.hole_cards, ctx.obs.board, n, weight)
        if eq_called < p["river_value_need"]:
            return 0
        return 2 if eq_called >= p["post_pot_size_eq"] else 1

    def river_bluff(self, ctx: Ctx, eq: float):
        """Bluff air on the river when the opponent's measured fold rate to
        our river bets pays for it. A half-pot bet risks 0.5 to win 1 (needs
        33% folds), a pot bet risks 1 to win 1 (needs 50%); we also give up
        our showdown equity. Stations never clear the bar, so this switches
        itself off against them."""
        p, opp = self.p, self.brain.opponent
        if not p["river_bluff_adapt"] or eq > p["river_bluff_max_eq"]:
            return None
        best, best_edge = None, p["river_bluff_margin"]
        for action, rate, risk in ((Action.RAISE_HALF, opp.river_fold_half, 0.5),
                                   (Action.RAISE_POT, opp.river_fold_pot, 1.0)):
            if rate.total < p["river_bluff_min_obs"]:
                continue
            f = rate.value
            edge = f - (1 - f) * risk - eq
            if edge > best_edge:
                best, best_edge = action, edge
        if best is None:
            return None
        if self.brain.rng.random() < p["river_bluff_adapt"] * self.brain.image.bluff_scale(p):
            return best
        return None

    def call_odds(self, ctx: Ctx) -> float:
        """Equity needed to call before the river. An opponent that keeps
        betting will charge us again on later streets, so the price moves
        from the pot odds toward the all-in odds by how often they bet."""
        if ctx.street == Street.RIVER:
            return ctx.pot_odds
        barrel = self.brain.opponent.rates["aggression"].value
        later = 1 if ctx.street == Street.TURN else 2
        weight = min(1.0, barrel * later * self.p["barrel_weight"])
        return ctx.pot_odds + weight * max(0.0, ctx.allin_odds - ctx.pot_odds)

    def committed(self, ctx: Ctx, eq: float) -> Action:
        """Calling commits our stack: decide with all-in odds, and shove
        rather than call when we are a favourite (no free cards)."""
        if eq >= self.p["commit_shove_eq"] and ctx.can_raise:
            return ctx.raise_(Action.RAISE_POT)
        if eq >= ctx.allin_odds:
            return ctx.call()
        return ctx.fold()

    def draw_raise(self, ctx: Ctx, eq: float) -> bool:
        """Semi-bluff raise a flop/turn bet with a real draw against a
        frequent bettor: their range is wide, so the raise often wins the
        pot now, and the draw keeps equity when called."""
        p = self.p
        if not p["draw_raise"] or ctx.street == Street.RIVER or eq < p["semi_bluff_min_eq"]:
            return False
        if self.brain.opponent.rate("aggression") < p["draw_raise_agg"]:
            return False
        if not has_draw(ctx.obs.hole_cards, ctx.obs.board):
            return False
        return self.brain.rng.random() < p["draw_raise"] * self.brain.image.bluff_scale(p)

    def should_bluff(self, ctx: Ctx, eq: float) -> bool:
        """Semi-bluff real draws before the river; rarely bluff air on the
        river from position. Opponent modeling scales these later."""
        p, rng = self.p, self.brain.rng
        scale = self.brain.image.bluff_scale(p)
        if ctx.street != Street.RIVER:
            if eq >= p["semi_bluff_min_eq"] and has_draw(ctx.obs.hole_cards, ctx.obs.board):
                return rng.random() < p["semi_bluff_freq"] * scale
            return False
        if ctx.in_position and eq <= p["river_bluff_max_eq"]:
            return rng.random() < p["river_bluff_freq"] * scale
        return False

    # ------------------------------------------------------------------
    @staticmethod
    def _blend(prior: float, estimate: float, n: float, k: float) -> float:
        """Move from the prior to the estimate as evidence (n) accumulates."""
        w = n / (n + k)
        return (1 - w) * prior + w * estimate

    def range_floor(self, opp_raises: int) -> float:
        """Percentile floor of the opponent's preflop range after n raises.

        Starts at the parameter prior; as hands accumulate it moves toward
        1 - (their raise frequency), i.e. "they raise their top X%", and
        showdowns of their raising hands refine it."""
        if opp_raises <= 0:
            return 0.0
        p, opp = self.p, self.brain.opponent
        if not p["learn_preflop"]:
            return (p["range_floor_1raise"], p["range_floor_2raise"],
                    p["range_floor_3raise"])[min(opp_raises, 3) - 1]
        pfr = opp.rates["pfr"]
        freq_floor = min(0.92, max(0.05, 1.0 - pfr.value))
        floor1 = self._blend(p["range_floor_1raise"], freq_floor, pfr.total, 30.0)
        floor1 = self.brain.showdowns.raise_floor(floor1)
        if opp_raises == 1:
            return floor1
        tb = opp.rates["three_bet"]
        step = self._blend(p["range_floor_2raise"], min(0.95, max(floor1, 1.0 - tb.value * (1 - floor1))),
                           tb.total, 20.0)
        floor2 = max(floor1, step)
        if opp_raises == 2:
            return floor2
        return max(floor2, p["range_floor_3raise"])

    def call_floor(self) -> float:
        if not self.p["learn_preflop"]:
            return self.p["range_floor_call"]
        return self.brain.showdowns.call_floor(self.p["range_floor_call"])

    def equity_vs_range(self, ctx: Ctx, floor: float, marks=()) -> float:
        eq = self.estimate(ctx, ranges.preflop_floor(floor), marks)
        if eq < 0:
            # Out of time: approximate from the table (a tighter range costs equity).
            return preflop.equity(ctx.obs.hole_cards) - 0.12 * floor
        return eq

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
        margin = p["pre_call_margin_ip"] if ctx.in_position else p["pre_call_margin_oop"]
        if not p["adaptive_samples"]:
            marks = ()
        elif ctx.committed_after_call(p["commit_ratio"]):
            marks = (p["commit_shove_eq"], ctx.allin_odds)
        else:
            marks = (p["pre_reraise_equity"], ctx.pot_odds + margin)
        eq = self.equity_vs_range(ctx, floor, marks)
        if ctx.committed_after_call(p["commit_ratio"]):
            return self.committed(ctx, eq)
        if eq >= p["pre_reraise_equity"] and ctx.can_raise:
            return ctx.raise_(Action.RAISE_POT)
        if eq >= ctx.pot_odds + margin:
            return ctx.call()
        return ctx.fold()
