"""Guards that keep the bot from ever sending an error to the judge.

Five errors in one half forfeit the whole match, so every entry point is
wrapped: exceptions are swallowed and anything that is not a legal action
is replaced by CHECK_CALL, which is legal in every state.
"""

from __future__ import annotations

from game import Action, Observation


def fallback_action(obs: Observation) -> Action:
    """The action to play when our own logic fails: always legal."""
    return Action.CHECK_CALL


def ensure_legal(action, obs: Observation) -> Action:
    """Return `action` if it is a legal Action right now, else the fallback."""
    try:
        action = Action(action)
    except (ValueError, TypeError):
        return fallback_action(obs)
    if action in obs.legal_actions:
        return action
    # A raise that is no longer allowed (cap reached, opponent all-in) is
    # downgraded to a call rather than given up.
    return fallback_action(obs)
