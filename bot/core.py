"""The per-half "brain": owns every piece of state the bot keeps.

The judge gives us a fresh `memory` dict each half and the tournament
starts a fresh process each half, so all state hangs off one Brain object
stored in memory["brain"].
"""

from __future__ import annotations

import random
import time

from game import Action, AgentConfig, HandResult, Observation
from bot import fasteval, preflop  # noqa: F401  (load lookup tables at server startup)
from bot import params as params_mod
from bot.context import Ctx
from bot.equity import EquityEngine
from bot.image import SelfImage
from bot.opponent import RAISES, OpponentModel
from bot.autopilot import AutopilotDetector
from bot.profile import Profiler
from bot.showdown import ShowdownLearner
from bot.strategy import Strategy
from bot.timebank import FALLBACK_HEADROOM, TimeBank

BRAIN_KEY = "brain"

# Optional parameter overrides, set by the offline tuner before a half starts.
PARAM_OVERRIDES: dict = {}


class Brain:
    """All state for one half-match."""

    def __init__(self, config: AgentConfig, overrides: dict | None = None) -> None:
        self.config = config
        self.params = params_mod.make(overrides if overrides is not None else PARAM_OVERRIDES)
        self.hands_seen = 0
        self.timebank = TimeBank(config.time_bank_seconds, config.num_hands)
        self.engine = EquityEngine(seed=20261107)
        self.rng = random.Random(1107)
        self.opponent = OpponentModel()
        self.showdowns = ShowdownLearner(seed=7)
        self.profiler = Profiler(self.params)
        self.autopilot = AutopilotDetector()
        self.image = SelfImage()
        self._hand_index = -1
        self._history = ()
        self._my_last = None
        self.strategy = Strategy(self)

    # --- services used by the strategy ---------------------------------

    def samples(self, ctx: Ctx) -> int:
        n = self.timebank.samples(ctx.obs.hand_index)
        if n == 0 and self.timebank.charged_estimate() < self.timebank.bank - FALLBACK_HEADROOM:
            n = 40   # logic share used up, but the bank itself is fine: cheap estimate
        return n

    def equity(self, hole, board, n: int, weight_fn=None) -> float:
        start = time.perf_counter()
        eq = self.engine.equity(hole, board, n, weight_fn)
        self.timebank.record_samples(n, time.perf_counter() - start)
        return eq

    # --- entry points --------------------------------------------------

    def choose(self, obs: Observation) -> Action:
        """Pick an action for the current decision (timed)."""
        self.timebank.begin()
        try:
            self.timebank.decisions += 1
            action = self.strategy.decide(Ctx(obs))
            self._hand_index, self._history, self._my_last = obs.hand_index, obs.action_history, action
            return action
        finally:
            self.timebank.end(is_request=True)

    def hand_end(self, result: HandResult) -> None:
        """Learn from a finished hand (timed, but rides along with a request)."""
        self.timebank.begin()
        try:
            self.hands_seen += 1
            self.learn(result)
        finally:
            self.timebank.end(is_request=False)

    def learn(self, result: HandResult) -> None:
        if self._hand_index == result.hand_index:
            history, my_last = self._history, self._my_last
        else:                       # we never acted this hand (opponent folded first)
            history, my_last = (), None
        steps = OpponentModel.rebuild(history, my_last, result)
        self.opponent.observe_hand(steps, result)
        self.autopilot.observe(*OpponentModel.opponent_facing(steps))
        self.image.observe(steps)
        if result.went_to_showdown and result.opp_hole and len(result.board) == 5:
            we_raised = any(s.is_me and s.street == 0 and s.action in RAISES for s in steps)
            self.showdowns.add(result.opp_hole, result.board, [s for s in steps if not s.is_me],
                               we_raised)
        if self.params.get("exploit", 1.0) and self.profiler.update(self.opponent):
            self.strategy.p = self.profiler.params


def get_brain(memory: dict, config: AgentConfig | None = None) -> Brain:
    """Return this half's Brain, creating one if new_half failed or was skipped."""
    brain = memory.get(BRAIN_KEY)
    if not isinstance(brain, Brain):
        brain = Brain(config or AgentConfig())
        memory[BRAIN_KEY] = brain
    return brain


def new_half(config: AgentConfig, memory: dict) -> None:
    memory[BRAIN_KEY] = Brain(config)


def choose(obs: Observation, memory: dict) -> Action:
    return get_brain(memory).choose(obs)


def hand_end(result: HandResult, memory: dict) -> None:
    get_brain(memory).hand_end(result)
