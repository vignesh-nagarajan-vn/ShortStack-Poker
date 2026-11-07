"""Play duplicate matches in-process, scored exactly like judge_engine.py.

    python -m sim.run_match --a agent --b baseline_random --deals 1000 --seeds 1 2 3

Half 1 puts bot A in seat 0, half 2 in seat 1, on the same deals. Paired
per-deal results give the bb/deal mean, the 95% CI and the verdict through
judge_engine.decide_verdict. Errors, forfeits (5 errors) and a time bank
are modelled too: bots that run out of thinking time play check-or-fold.
"""

from __future__ import annotations

import argparse
import math
import statistics
import time
from dataclasses import dataclass, field
from typing import Callable

from sim.players import Player  # sets up sys.path for the root modules
from game import (BIG_BLIND, ERROR_LIMIT, NUM_DEALS, TIME_BANK_SECONDS, AgentConfig, Game,
                  button_for_deal, default_action, make_deal)
from judge_engine import CHOP_Z, decide_verdict

Factory = Callable[[AgentConfig], Player]


@dataclass
class SeatStats:
    """What one bot did during one half."""

    name: str
    calls: int = 0
    errors: int = 0
    time_seconds: float = 0.0
    forfeited: bool = False
    bank_empty: bool = False
    first_error: str = ""


@dataclass
class HalfOutcome:
    nets_a: list[int]
    stats: dict[str, SeatStats]


@dataclass
class MatchOutcome:
    a: str
    b: str
    seed: str
    mean_bb: float
    ci: tuple[float, float]
    verdict: str            # "A", "B", "CHOP" or "BOTH_FORFEIT"
    points_a: float
    halves: list[HalfOutcome] = field(default_factory=list)

    def summary(self) -> str:
        parts = []
        for i, h in enumerate(self.halves):
            s = h.stats["A"]
            flags = (" FORFEIT" if s.forfeited else "") + (" BANK_EMPTY" if s.bank_empty else "")
            parts.append(f"[A h{i + 1}: {s.time_seconds:.2f}s/{s.calls} err={s.errors}{flags}]")
            if s.first_error:
                parts.append(f"(A error: {s.first_error})")
        return (f"{self.a} vs {self.b} seed={self.seed}: {self.mean_bb:+.3f} bb/deal "
                f"CI [{self.ci[0]:+.3f}, {self.ci[1]:+.3f}] -> {self.verdict} " + " ".join(parts))


def _safe_hand_end(player: Player, stats: SeatStats, result) -> None:
    if stats.forfeited:
        return
    start = time.perf_counter()
    try:
        player.hand_end(result)
    except Exception as exc:  # counts as an error, like the judge
        stats.errors += 1
        stats.first_error = stats.first_error or f"hand_end: {type(exc).__name__}: {exc}"
    stats.time_seconds += time.perf_counter() - start
    if stats.errors >= ERROR_LIMIT:
        stats.forfeited = True


def play_half(make_a: Factory, make_b: Factory, seed, half: int, num_deals: int = NUM_DEALS,
              time_bank: float = TIME_BANK_SECONDS) -> HalfOutcome:
    """One half: A sits in seat 0 in half 1 and in seat 1 in half 2."""
    config = AgentConfig(num_hands=num_deals)
    a_seat = 0 if half == 1 else 1
    players = {"A": make_a(config), "B": make_b(config)}
    stats = {key: SeatStats(getattr(p, "name", key)) for key, p in players.items()}
    who = {a_seat: "A", 1 - a_seat: "B"}
    nets_a: list[int] = []
    for deal_index in range(num_deals):
        game = Game(make_deal(str(seed), deal_index), button_for_deal(deal_index), deal_index)
        while not game.is_terminal:
            seat = game.to_act
            key = who[seat]
            st = stats[key]
            obs = game.observation(seat)
            action = None
            if not st.forfeited and st.time_seconds < time_bank:
                start = time.perf_counter()
                try:
                    action = players[key].act(obs)
                except Exception as exc:
                    st.errors += 1
                    st.first_error = st.first_error or f"act: {type(exc).__name__}: {exc}"
                    action = None
                elapsed = time.perf_counter() - start
                st.time_seconds += elapsed
                st.calls += 1
                if elapsed > 1.0:
                    st.errors += 1
                    st.first_error = st.first_error or f"act took {elapsed:.2f}s"
                    action = None
                elif action is not None and action not in obs.legal_actions:
                    st.errors += 1
                    st.first_error = st.first_error or f"illegal {action!r}"
                    action = None
                if st.errors >= ERROR_LIMIT:
                    st.forfeited = True
                if st.time_seconds >= time_bank:
                    st.bank_empty = True
            if action is None:
                action = default_action(obs.to_call)
            game.apply(action)
        nets_a.append(game.result().nets[a_seat])
        for seat, key in who.items():
            _safe_hand_end(players[key], stats[key], game.hand_result(seat))
    return HalfOutcome(nets_a=nets_a, stats=stats)


def score(nets1: list[int], nets2: list[int]) -> tuple[float, tuple[float, float]]:
    """Paired bb/deal mean and 95% CI, the same arithmetic as the judge."""
    n = len(nets1)
    paired_bb = [(nets1[d] + nets2[d]) / BIG_BLIND for d in range(n)]
    mean = sum(paired_bb) / n
    std = statistics.stdev(paired_bb) if n > 1 else 0.0
    stderr = std / math.sqrt(n)
    return mean, (mean - CHOP_Z * stderr, mean + CHOP_Z * stderr)


def play_match(make_a: Factory, make_b: Factory, seed, num_deals: int = NUM_DEALS,
               time_bank: float = TIME_BANK_SECONDS) -> MatchOutcome:
    """Both halves on the same deals, then the judge's verdict rules."""
    h1 = play_half(make_a, make_b, seed, 1, num_deals, time_bank)
    h2 = play_half(make_a, make_b, seed, 2, num_deals, time_bank)
    mean, ci = score(h1.nets_a, h2.nets_a)
    verdict_raw, _, _ = decide_verdict(*ci)
    verdict = {"AGENT1_WIN": "A", "AGENT2_WIN": "B"}.get(verdict_raw, "CHOP")
    a_forfeit = h1.stats["A"].forfeited or h2.stats["A"].forfeited
    b_forfeit = h1.stats["B"].forfeited or h2.stats["B"].forfeited
    if a_forfeit and b_forfeit:
        verdict = "BOTH_FORFEIT"
    elif a_forfeit:
        verdict = "B"
    elif b_forfeit:
        verdict = "A"
    points_a = {"A": 1.0, "B": 0.0, "CHOP": 0.5, "BOTH_FORFEIT": 0.0}[verdict]
    return MatchOutcome(a=h1.stats["A"].name, b=h1.stats["B"].name, seed=str(seed),
                        mean_bb=mean, ci=ci, verdict=verdict, points_a=points_a, halves=[h1, h2])


def main() -> None:
    from sim.pool import resolve

    parser = argparse.ArgumentParser(description="Play in-process duplicate matches.")
    parser.add_argument("--a", default="agent", help="bot A (pool name or path to an agent-style file)")
    parser.add_argument("--b", default="baseline_random", help="bot B")
    parser.add_argument("--deals", type=int, default=NUM_DEALS)
    parser.add_argument("--seeds", nargs="+", default=["1"])
    args = parser.parse_args()
    for seed in args.seeds:
        print(play_match(resolve(args.a), resolve(args.b), seed, args.deals).summary(), flush=True)


if __name__ == "__main__":
    main()
