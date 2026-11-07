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
