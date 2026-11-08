"""Where do the chips come from? Decision statistics for our bot per opponent.

    python -m sim.probe --opps brown barreler range_pro --seeds 1 2
    python -m sim.probe --set river_bluff_adapt=1 --opps nit

Plays full duplicate matches with an instrumented BrainPlayer and prints,
per opponent: postflop fold-to-bet by street and how often the fold gave
up the best hand (we know the deal in the simulator), river bets called
and won, river bluff success, preflop open/defend frequencies, and the
bb/deal.
"""

from __future__ import annotations

import os

os.environ.setdefault("OMP_NUM_THREADS", "1")

import argparse  # noqa: E402
from collections import defaultdict  # noqa: E402
from concurrent.futures import ProcessPoolExecutor  # noqa: E402

from sim.players import BrainPlayer, class_factory  # noqa: E402
from game import Action, Street, make_deal  # noqa: E402
from evaluator import omaha_score  # noqa: E402

RAISES = (Action.RAISE_HALF, Action.RAISE_POT)


class ProbePlayer(BrainPlayer):
    def __init__(self, config, overrides=None, seed="1", counts=None):
        super().__init__(config, overrides)
        self.seed = str(seed)
        self.c = counts if counts is not None else defaultdict(float)
        self.hand = []

    def act(self, obs):
        action = super().act(obs)
        self.hand.append((obs, action))
        return action

    def hand_end(self, result):
        super().hand_end(result)
        c, hand, self.hand = self.c, self.hand, []
        if not hand:
            return
        deal = make_deal(self.seed, result.hand_index)
        mine = hand[0][0].hole_cards
        opp = deal.hole_cards[1] if tuple(deal.hole_cards[0]) == tuple(mine) else deal.hole_cards[0]
        we_best = omaha_score(list(mine), list(deal.board)) > omaha_score(list(opp), list(deal.board))
        bb = 2.0
        for obs, action in hand:
            st = obs.street.name.lower()
            if obs.street == Street.PREFLOP:
                opp_raised = any(not a.is_me and a.action in RAISES for a in obs.action_history)
                if obs.is_button and not obs.action_history:
                    c["sb_open"] += 1
                    c["sb_fold"] += action == Action.FOLD
                    c["sb_raise"] += action in RAISES
                elif opp_raised and obs.to_call > 0:
                    c["pre_face"] += 1
                    c["pre_face_fold"] += action == Action.FOLD
                    c["pre_face_call"] += action == Action.CHECK_CALL
                    c["pre_face_raise"] += action in RAISES
                continue
            if obs.to_call > 0:
                c[f"{st}_face"] += 1
                if action == Action.FOLD:
                    c[f"{st}_fold"] += 1
                    c[f"{st}_fold_best"] += we_best
                    c[f"{st}_fold_best_pot"] += we_best * obs.pot / bb
                elif action in RAISES:
                    c[f"{st}_raise"] += 1
            else:
                c[f"{st}_free"] += 1
                c[f"{st}_bet"] += action in RAISES
        last_obs, last_act = hand[-1]
        if last_obs.street == Street.RIVER and last_act in RAISES and last_obs.to_call == 0:
            if result.went_to_showdown:
                c["rv_called"] += 1
                c["rv_called_won"] += result.winner == "me"
            elif result.winner == "me":
                c["rv_folded"] += 1
                c["rv_folded_bluff"] += not we_best
        c["hands"] += 1
        c["net_bb"] += result.my_net / bb


def _job(job):
    overrides, opp, seed, deals = job
    from sim.pool import resolve
    from sim.run_match import play_match
    counts = defaultdict(float)
    me = class_factory(ProbePlayer, "probe", overrides=overrides, seed=seed, counts=counts)
    out = play_match(me, resolve(opp), seed, deals)
    return opp, dict(counts), out.mean_bb


def pct(a, b):
    return f"{100 * a / b:5.1f}%" if b else "    -"


def main():
    from sim.ab import parse_overrides
    parser = argparse.ArgumentParser()
    parser.add_argument("--opps", nargs="+", required=True)
    parser.add_argument("--seeds", nargs="+", default=["1", "2"])
    parser.add_argument("--deals", type=int, default=1000)
    parser.add_argument("--set", default="", help="param overrides k=v,k2=v2")
    args = parser.parse_args()
    _, overrides = parse_overrides(args.set)
    jobs = [(overrides, o, s, args.deals) for o in args.opps for s in args.seeds]
    agg = defaultdict(lambda: defaultdict(float))
    bbs = defaultdict(list)
    with ProcessPoolExecutor(max_workers=min(len(jobs), (os.cpu_count() or 2) - 1)) as pool:
        for opp, counts, mean in pool.map(_job, jobs):
            for k, v in counts.items():
                agg[opp][k] += v
            bbs[opp].append(mean)
    for opp in args.opps:
        c = agg[opp]
        print(f"\n== {opp}: {sum(bbs[opp]) / len(bbs[opp]):+.3f} bb/deal over {len(bbs[opp])} matches")
        print(f"  preflop  SB fold {pct(c['sb_fold'], c['sb_open'])} raise {pct(c['sb_raise'], c['sb_open'])}"
              f" | facing raise: fold {pct(c['pre_face_fold'], c['pre_face'])} call "
              f"{pct(c['pre_face_call'], c['pre_face'])} 3bet {pct(c['pre_face_raise'], c['pre_face'])}")
        for st in ("flop", "turn", "river"):
            print(f"  {st:<6} faced {int(c[st + '_face']):5d}: fold {pct(c[st + '_fold'], c[st + '_face'])}"
                  f" (gave up best hand {pct(c[st + '_fold_best'], c[st + '_fold'])},"
                  f" {c[st + '_fold_best_pot']:7.0f} bb of pots) raise {pct(c[st + '_raise'], c[st + '_face'])}"
                  f" | checked to {int(c[st + '_free']):5d}: bet {pct(c[st + '_bet'], c[st + '_free'])}")
        print(f"  river bets: called {int(c['rv_called'])} won {pct(c['rv_called_won'], c['rv_called'])}"
              f" | folded {int(c['rv_folded'])} (of which bluffs {int(c['rv_folded_bluff'])})")


if __name__ == "__main__":
    main()
