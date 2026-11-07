"""The per-half "brain": owns every piece of state the bot keeps.

The judge gives us a fresh `memory` dict each half and the tournament
starts a fresh process each half, so all state hangs off one Brain object
stored in memory["brain"].
"""

from __future__ import annotations

from game import Action, AgentConfig, HandResult, Observation

BRAIN_KEY = "brain"


class Brain:
    """All state for one half-match."""

    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self.hands_seen = 0

    def choose(self, obs: Observation) -> Action:
        """Pick an action for the current decision."""
        return Action.CHECK_CALL

    def hand_end(self, result: HandResult) -> None:
        """Learn from a finished hand."""
        self.hands_seen += 1


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
