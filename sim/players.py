"""A small Player interface so any bot can play in-process (no HTTP).

A Player is created once per half (matching the tournament, which starts a
fresh server every half) and answers act() for each decision.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from typing import Callable

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from game import Action, AgentConfig, HandResult, Observation  # noqa: E402


class Player:
    """Base class: override act(), optionally hand_end()."""

    name = "player"

    def __init__(self, config: AgentConfig) -> None:
        self.config = config

    def act(self, obs: Observation) -> Action:
        raise NotImplementedError

    def hand_end(self, result: HandResult) -> None:
        pass


class ModulePlayer(Player):
    """Wraps an agent.py-style module (new_half / choose_action / on_hand_end)."""

    def __init__(self, config: AgentConfig, module, name: str) -> None:
        super().__init__(config)
        self.module = module
        self.name = name
        self.memory: dict = {}
        module.new_half(config, self.memory)

    def act(self, obs: Observation) -> Action:
        return self.module.choose_action(obs, self.memory)

    def hand_end(self, result: HandResult) -> None:
        self.module.on_hand_end(result, self.memory)


_MODULE_CACHE: dict[str, object] = {}


def load_module(path: str):
    """Import an agent-style file by path (cached; each gets its own module)."""
    path = os.path.abspath(path)
    if path not in _MODULE_CACHE:
        name = "simbot_" + os.path.splitext(os.path.basename(path))[0]
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _MODULE_CACHE[path] = module
    return _MODULE_CACHE[path]


def module_factory(path: str, name: str | None = None) -> Callable[[AgentConfig], Player]:
    """A factory that builds a fresh ModulePlayer for each half."""
    label = name or os.path.splitext(os.path.basename(path))[0]

    def make(config: AgentConfig) -> Player:
        return ModulePlayer(config, load_module(path), label)

    make.label = label  # type: ignore[attr-defined]
    return make


def class_factory(cls, name: str, **kwargs) -> Callable[[AgentConfig], Player]:
    """A factory for a Player subclass with fixed keyword arguments."""

    def make(config: AgentConfig) -> Player:
        player = cls(config, **kwargs)
        player.name = name
        return player

    make.label = name  # type: ignore[attr-defined]
    return make


def agent_factory() -> Callable[[AgentConfig], Player]:
    """Our own bot, exactly as agent.py runs it (safety wrapper included)."""
    return module_factory(os.path.join(ROOT, "agent.py"), "shortstack")


class VirtualClock:
    """A deterministic stand-in for perf_counter: every reading costs `tick`
    seconds (so each timed decision costs about one tick) and each Monte
    Carlo call costs `per_call` plus `per_sample` per sample. These were
    0.45 ms + 4.5 us (measured with range weights, padded 30% to match the
    real-clock bot's sample counts in full matches). The November 2026
    engine speedup ran our bot's recorded equity calls in 0.54-0.58x the
    time, so they are now 0.32 ms + 2.5 us (the same padding, rounded up).
    run_match charges a virtual-time player by this clock too, so a
    machine stall can't empty its bank either. With it the bot's sample counts, and so
    its decisions, no longer depend on machine load, and an A/A test of
    identical parameters gives identical play. Defaults match this laptop:
    about 3.5 s of thinking per half, as on the real judge."""

    def __init__(self, tick: float = 0.0001, per_call: float = 0.00032,
                 per_sample: float = 2.5e-6) -> None:
        self.t = 0.0
        self.tick, self.per_call, self.per_sample = tick, per_call, per_sample

    def __call__(self) -> float:
        self.t += self.tick
        return self.t

    def charge_samples(self, n: int) -> None:
        self.t += self.per_call + n * self.per_sample


# Set False (sim.ab --real-time) to time our bot with the real clock.
VIRTUAL_TIME = True


class BrainPlayer(Player):
    """Our bot built directly from bot.core.Brain with parameter overrides,
    wrapped in the same safety checks as agent.py. Used for self-play
    (earlier versions, ablations) and for parameter tuning. Times itself
    with a VirtualClock unless VIRTUAL_TIME is off."""

    def __init__(self, config: AgentConfig, overrides: dict | None = None,
                 virtual_time: bool | None = None, clock_costs: dict | None = None) -> None:
        super().__init__(config)
        from bot.core import Brain
        virtual = VIRTUAL_TIME if virtual_time is None else virtual_time
        self.clock = VirtualClock(**(clock_costs or {})) if virtual else None
        self.brain = Brain(config, overrides or {}, clock=self.clock)

    def act(self, obs: Observation) -> Action:
        from bot.safety import ensure_legal, fallback_action
        try:
            return ensure_legal(self.brain.choose(obs), obs)
        except Exception:
            return fallback_action(obs)

    def hand_end(self, result: HandResult) -> None:
        try:
            self.brain.hand_end(result)
        except Exception:
            pass
