"""
Tests for YOUR bot (agent.py). Run them from the bundle folder:

    python -m pytest -q

They talk to your bot the same way the judge does (through its web routes,
but without starting a real server), so a passing run means the judge can
play with your bot. Add your own tests at the bottom!
"""

import importlib.util
import os
import random
import sys

import pytest
from fastapi.testclient import TestClient

# Works whether this file sits next to agent.py or inside a tests/ folder.
HERE = os.path.dirname(os.path.abspath(__file__))
BUNDLE = HERE if os.path.isfile(os.path.join(HERE, "game.py")) else os.path.dirname(HERE)
sys.path.insert(0, BUNDLE)  # so agent.py can import game.py and evaluator.py

from game import Action, AgentConfig, Game, make_deal  # noqa: E402
from judge_engine import coerce_action  # noqa: E402  (reads answers exactly like the judge)

TOKEN = "test-token"
AUTH = {"X-Agent-Token": TOKEN}


def load_agent():
    """Load a fresh copy of agent.py (its own MEMORY and globals)."""
    spec = importlib.util.spec_from_file_location("agent_under_test", os.path.join(BUNDLE, "agent.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def bot():
    """(agent module, test client) with the tournament's token check switched on."""
    module = load_agent()
    module.TOKEN = TOKEN
    return module, TestClient(module.app)


def start_half(client, half=1, seat=0):
    """POST /new-half the way the judge does."""
    body = {"half": half, "seat": seat, "config": AgentConfig().to_dict()}
    return client.post("/new-half", json=body, headers=AUTH)


def play_hands(client, num_hands, seed="test", raise_rate=0.3):
    """Play hands where YOUR bot is seat 0 and a random opponent is seat 1.

    Every decision goes through /act exactly like in a real match, and
    finished hands are delivered with the next /act (like the judge does).
    Returns the list of every action your bot chose.
    """
    rng = random.Random(seed)
    pending = []      # finished hands waiting to be delivered
    chosen = []
    for hand in range(num_hands):
        game = Game(make_deal(seed, hand), button_seat=hand % 2, hand_index=hand)
        while not game.is_terminal:
            seat = game.to_act
            obs = game.observation(seat)
            if seat == 0:
                r = client.post("/act", json={"observation": obs.to_dict(), "hand_results": pending},
                                headers=AUTH)
                pending = []
                assert r.status_code == 200, f"/act failed: {r.json()}"
                reply = r.json()
                assert reply.get("hand_end_errors", []) == [], \
                    f"on_hand_end crashed: {reply['hand_end_errors'][0]['traceback']}"
                action = coerce_action(reply["action"])
                assert action in obs.legal_actions, \
                    f"choose_action returned {reply['action']!r}; legal were {[a.name for a in obs.legal_actions]}"
                chosen.append(action)
            else:
                # Random opponent that raises sometimes, so your bot faces bets.
                raises = [a for a in obs.legal_actions if a in (Action.RAISE_HALF, Action.RAISE_POT)]
                action = rng.choice(raises) if raises and rng.random() < raise_rate else Action.CHECK_CALL
            game.apply(action)
        pending.append(game.hand_result(0).to_dict())
    r = client.post("/hand-end", json={"results": pending}, headers=AUTH)  # end of half
    assert r.status_code == 200 and r.json()["hand_end_errors"] == []
    return chosen


# ---------------------------------------------------------------------------
# Your bot plays correctly
# ---------------------------------------------------------------------------

def test_names_are_set(bot):
    _, client = bot
    info = client.get("/").json()
    assert isinstance(info["participant"], str) and info["participant"]
    assert isinstance(info["agent_name"], str) and info["agent_name"]


def test_new_half_works(bot):
    _, client = bot
    r = start_half(client)
    assert r.status_code == 200, f"new_half crashed: {r.json()}"


def test_every_decision_is_legal(bot):
    # 200 hands with a random opponent: every choose_action answer must be legal.
    _, client = bot
    start_half(client)
    play_hands(client, 200)


def test_works_in_both_seats_and_both_halves(bot):
    _, client = bot
    for half, seat in ((1, 0), (2, 1)):
        assert start_half(client, half, seat).status_code == 200
        play_hands(client, 30, seed=f"half{half}")


def test_handles_aggressive_opponent(bot):
    # An opponent that raises whenever it can: your bot must cope with
    # big bets and all-ins.
    _, client = bot
    start_half(client)
    play_hands(client, 100, seed="aggressive", raise_rate=1.0)


def test_memory_is_fresh_each_half(bot):
    module, client = bot
    start_half(client)
    play_hands(client, 10)
    start_half(client, half=2, seat=1)
    after_reset = dict(module.MEMORY)
    fresh = load_agent()
    fresh.new_half(AgentConfig(), fresh.MEMORY)
    assert after_reset.keys() == fresh.MEMORY.keys(), "memory should only hold what new_half() puts there"


# ---------------------------------------------------------------------------
# The server plumbing still works (only fails if you edited it)
# ---------------------------------------------------------------------------

def test_token_is_checked(bot):
    _, client = bot
    body = {"half": 1, "seat": 0, "config": {}}
    assert client.post("/new-half", json=body).status_code == 401
    assert client.post("/new-half", json=body, headers={"X-Agent-Token": "wrong"}).status_code == 401


def test_bad_token_is_refused_before_the_body_is_read(bot):
    # Without the right token the bot must answer 401 without parsing the body,
    # so junk sent by anyone else can't slow your bot down.
    _, client = bot
    junk = b"this is not JSON" * 1000
    assert client.post("/act", content=junk).status_code == 401
    assert client.post("/act", content=junk, headers={"X-Agent-Token": "wrong"}).status_code == 401


def test_malformed_body_is_rejected(bot):
    _, client = bot
    start_half(client)
    assert client.post("/act", content=b"not json", headers=AUTH).status_code == 400
    assert client.post("/act", json=[1, 2, 3], headers=AUTH).status_code == 400


def test_act_before_new_half_is_refused(bot):
    _, client = bot
    obs = Game(make_deal(1, 0), 0).observation(0).to_dict()
    assert client.post("/act", json={"observation": obs, "hand_results": []}, headers=AUTH).status_code == 409


def test_crashes_are_reported_to_the_judge(bot):
    # If choose_action raises, the judge must get a 500 with your traceback.
    module, client = bot

    def broken(obs, memory):
        raise ValueError("oops")

    module.choose_action = broken
    start_half(client)
    obs = Game(make_deal(1, 0), 0).observation(0).to_dict()
    r = client.post("/act", json={"observation": obs, "hand_results": []}, headers=AUTH)
    assert r.status_code == 500
    assert "ValueError: oops" in r.json()["error"] and "Traceback" in r.json()["traceback"]


def test_reads_port_from_environment():
    source = open(os.path.join(BUNDLE, "agent.py"), encoding="utf-8").read()
    assert 'os.environ.get("PORT"' in source, "agent.py must read its port from $PORT"
    assert '0.0.0.0' in source, "agent.py must listen on 0.0.0.0 so the judge can reach it"


# ---------------------------------------------------------------------------
# Add your own tests below, e.g. "with two aces preflop my bot raises".
# ---------------------------------------------------------------------------


# ---- ShortStack hardening tests -------------------------------------------

def _random_states(n, seed=11):
    """Yield (game, seat) pairs from random play, covering every street,
    all-ins, the raise cap and both seats."""
    rng = random.Random(seed)
    produced = 0
    hand = 0
    while produced < n:
        game = Game(make_deal(f"fuzz{seed}", hand), button_seat=hand % 2, hand_index=hand % 1000)
        hand += 1
        while not game.is_terminal and produced < n:
            yield game, game.to_act
            produced += 1
            legal = game.legal_actions()
            weights = [3 if a in (Action.RAISE_HALF, Action.RAISE_POT) else 1 for a in legal]
            game.apply(rng.choices(legal, weights)[0])


def test_fuzz_every_decision_is_legal():
    # Thousands of random states straight through the agent's functions.
    module = load_agent()
    module.new_half(AgentConfig(), module.MEMORY)
    for game, seat in _random_states(4000):
        obs = game.observation(seat)
        action = module.choose_action(obs, module.MEMORY)
        assert action in obs.legal_actions, (obs, action)


def test_survives_missing_or_corrupted_memory():
    module = load_agent()
    game = Game(make_deal(3, 0), 0)
    obs = game.observation(game.to_act)
    assert module.choose_action(obs, {}) in obs.legal_actions          # new_half never ran
    assert module.choose_action(obs, {"brain": 42}) in obs.legal_actions


def test_on_hand_end_never_raises_on_odd_results():
    from game import HandResult
    module = load_agent()
    module.new_half(AgentConfig(), module.MEMORY)
    odd = [HandResult(5, 0, 4, True, (0, 1, 2, 3, 4), (5, 6, 7, 8, 9), "split"),
           HandResult(6, -1, 3, False, (), None, "opp"),
           HandResult(999, 2, 4, False, (0, 1, 2), None, "me")]
    for r in odd:
        module.on_hand_end(r, module.MEMORY)


def test_time_budget_holds_on_a_slow_machine():
    # Make every equity call twice as slow, then play a full half against a
    # bot that raises whenever it can (the most decisions per hand). Our own
    # thinking must stay well inside the 8 s bank, leaving room for the web
    # server's per-request overhead.
    import time as _time
    from bot.equity import EquityEngine
    from sim.players import BrainPlayer
    from sim.run_match import play_half
    from sim.players import class_factory
    from sim.opponents import Maniac

    real = EquityEngine.equity

    def slow(self, hole, board, n, weight_fn=None):
        start = _time.perf_counter()
        eq = real(self, hole, board, n, weight_fn)
        end = _time.perf_counter() + (_time.perf_counter() - start)   # burn the same time again
        while _time.perf_counter() < end:
            pass
        return eq

    EquityEngine.equity = slow
    try:
        out = play_half(lambda c: BrainPlayer(c), class_factory(Maniac, "maniac", raise_rate=1.0),
                        "slow", 1, 1000)
    finally:
        EquityEngine.equity = real
    st = out.stats["A"]
    assert st.errors == 0
    overhead = st.calls * 0.0006
    assert st.time_seconds + overhead < 6.5, f"{st.time_seconds:.2f}s thinking over {st.calls} calls"


def test_single_decision_is_fast():
    import time as _time
    module = load_agent()
    module.new_half(AgentConfig(), module.MEMORY)
    worst = 0.0
    for game, seat in _random_states(1500, seed=12):
        obs = game.observation(seat)
        start = _time.perf_counter()
        module.choose_action(obs, module.MEMORY)
        worst = max(worst, _time.perf_counter() - start)
    assert worst < 0.15, f"slowest decision took {worst * 1e3:.0f} ms (limit 1000 ms)"
