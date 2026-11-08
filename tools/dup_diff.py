"""Deal-by-deal duplicate diff of container matches (needs LOGS=1 half JSONs).

    python tools/dup_diff.py . shortstack_33977a2_vs_fjdanisaf_plo5-mccfr_latest 11 12 13 14

Reads results/container/{TAG_PREFIX}_s{SEED}_h{1,2}.json written by
LOGS=1 tools/container_match.sh.

agent1 (seat 0 in half 1, seat 1 in half 2) is "A" (ShortStack), agent2 "B".
Each deal's paired result equals A's net with a set of cards minus B's net
with the same cards, so each deal is attributed to the first decision where
the two halves' histories differ: there both bots faced the identical
history holding identical cards.
"""
import json
import sys
from collections import defaultdict

ROOT, PREFIX, SEEDS = sys.argv[1], sys.argv[2], sys.argv[3:]
sys.path.insert(0, ROOT)
from evaluator import omaha_score, str_to_card  # noqa: E402

BB = 2
STREETS = ["PREFLOP", "FLOP", "TURN", "RIVER"]
RAISES = ("RAISE_HALF", "RAISE_POT")


def logs_of(d):
    for k in ("logs", "hands", "hand_logs"):
        if k in d:
            return d[k]
    raise KeyError(f"no hand logs in JSON (keys {list(d)}); rerun with LOGS=1")


def cards(xs):
    return [str_to_card(x) for x in xs]


def best_seat(h):
    b = cards(h["board"])
    s = [omaha_score(cards(h["hole_cards"][i]), b) for i in (0, 1)]
    return 0 if s[0] > s[1] else 1 if s[1] > s[0] else -1


def spot(h, i):
    """Describe the decision at action index i: (street, facing, position)."""
    acts = h["actions"]
    a = acts[i]
    st = a["street"]
    prev = [x for x in acts[:i] if x["street"] == st]
    raises = sum(x["action"] in RAISES for x in prev)
    if st == "PREFLOP":
        facing = f"pre_r{raises}"          # r0 = SB first-in or BB vs limp
        if raises == 0 and a["seat"] != h["button_seat"]:
            facing = "pre_vs_limp"
        elif raises == 0:
            facing = "pre_first_in"
    else:
        facing = "vs_bet" if raises == 1 else f"vs_raise{raises}" if raises else "unopened"
    pos = "IP" if a["seat"] == h["button_seat"] else "OOP"
    return st, facing, pos


# --------------------------------------------------------------------------
div = defaultdict(lambda: [0, 0.0])          # (street, facing, A act, B act) -> [n, paired chips]
div_best = defaultdict(lambda: [0, 0, 0])    # fold spots: [n, folder had best final hand, other had]
ends = defaultdict(float)                    # A's chips by how the hand ended
stats = {b: defaultdict(lambda: [0, 0]) for b in "AB"}
gave_up = {b: defaultdict(lambda: [0, 0]) for b in "AB"}
bluffs = {b: defaultdict(lambda: [0, 0]) for b in "AB"}   # bets w/o best hand: [n, got fold]
sizes = {b: defaultdict(int) for b in "AB"}
total_paired, n_deals, identical = 0, 0, 0
paired_by_seed = {}

for seed in SEEDS:
    halves = [json.load(open(f"{ROOT}/results/container/{PREFIX}_s{seed}_h{k}.json")) for k in (1, 2)]
    L1, L2 = logs_of(halves[0]), logs_of(halves[1])
    sp = 0
    for h1, h2 in zip(L1, L2):
        assert h1["hole_cards"] == h2["hole_cards"] and h1["button_seat"] == h2["button_seat"]
        # seat -> bot: half 1 A is seat 0, half 2 A is seat 1
        for h, a_seat in ((h1, 0), (h2, 1)):
            who = {a_seat: "A", 1 - a_seat: "B"}
            best = best_seat(h)
            acts = h["actions"]
            last = acts[-1] if acts else None
            # how it ended, from A's view
            if last and last["action"] == "FOLD":
                key = f"{'A' if who[last['seat']] == 'A' else 'B'} folds {last['street'].lower()}"
            else:
                key = f"showdown ({acts[-1]['street'].lower() if acts else '?'} end)"
            ends[key] += h["nets"][a_seat]
            for i, a in enumerate(acts):
                b = who[a["seat"]]
                st, facing, pos = spot(h, i)
                k = (st, facing)
                stats[b][k + (a["action"],)][0] += 1
                stats[b][k + ("ALL",)][0] += 1
                if a["action"] in RAISES:
                    sizes[b][(st, a["action"])] += 1
                if st != "PREFLOP" and facing != "unopened" and a["action"] == "FOLD":
                    gave_up[b][st][0] += 1
                    gave_up[b][st][1] += best == a["seat"]
                if st != "PREFLOP" and facing == "unopened" and a["action"] in RAISES and best != a["seat"]:
                    bluffs[b][st][0] += 1
                    nxt = acts[i + 1] if i + 1 < len(acts) else None
                    bluffs[b][st][1] += bool(nxt and nxt["action"] == "FOLD")
        paired = h1["nets"][0] + h2["nets"][1]
        sp += paired
        n_deals += 1
        # first divergence
        A1, A2 = h1["actions"], h2["actions"]
        i = 0
        while i < min(len(A1), len(A2)) and (A1[i]["seat"], A1[i]["action"]) == (A2[i]["seat"], A2[i]["action"]):
            i += 1
        if i >= len(A1) and i >= len(A2):
            identical += 1
            div[("same line", "", "", "")][0] += 1
            div[("same line", "", "", "")][1] += paired
            continue
        seat = A1[i]["seat"]
        # half 1: seat 0 is A. So at seat 0, h1 action is A's, h2 is B's; at seat 1 the reverse.
        a_act = A1[i]["action"] if seat == 0 else A2[i]["action"]
        b_act = A2[i]["action"] if seat == 0 else A1[i]["action"]
        st, facing, pos = spot(h1, i)
        key = (st, f"{facing} {pos}", a_act, b_act)
        div[key][0] += 1
        div[key][1] += paired
        if "FOLD" in (a_act, b_act):
            best = best_seat(h1)
            div_best[key][0] += 1
            div_best[key][1] += best == seat
    paired_by_seed[seed] = sp / BB / len(L1)
    total_paired += sp

n_seeds = len(SEEDS)
print(f"deals {n_deals}, A bb/deal {total_paired / BB / n_deals:+.3f}  per seed "
      + "  ".join(f"{s}:{v:+.2f}" for s, v in paired_by_seed.items()))
print(f"identical lines: {identical} deals\n")


def bbpd(chips):  # chips summed over both halves -> bb/deal
    return chips / BB / n_deals


print("== A's result by how the hand ended (bb/deal)")
for k, v in sorted(ends.items(), key=lambda kv: kv[1]):
    print(f"  {k:28s} {bbpd(v):+.3f}")

print("\n== First divergence: same cards, same history, different choice")
print("   (paired bb/deal contribution; best% = player to act ends with the best hand)")
rows = sorted(div.items(), key=lambda kv: kv[1][1])
for (st, spot_, a, b), (n, ch) in rows:
    if n < 15 and abs(bbpd(ch)) < 0.02:
        continue
    extra = ""
    if (st, spot_, a, b) in div_best:
        nb, bst, _ = div_best[(st, spot_, a, b)]
        extra = f"  best {100 * bst / nb:4.0f}%"
    print(f"  {st:8s} {spot_:22s} A {a:10s} B {b:10s} n={n:5d} {bbpd(ch):+.3f}  avg {ch / n / BB:+6.2f} bb{extra}")

by_street = defaultdict(float)
for (st, *_), (n, ch) in div.items():
    by_street[st] += ch
print("\n  by street of first divergence: " + "  ".join(f"{s.lower()} {bbpd(v):+.3f}" for s, v in by_street.items()))

print("\n== Action frequencies (A = ShortStack, B = opponent)")
spots = sorted({k[:2] for b in "AB" for k in stats[b]}, key=lambda k: (STREETS.index(k[0]), k[1]))
for k in spots:
    line = f"  {k[0]:8s} {k[1]:13s}"
    for b in "AB":
        tot = stats[b][k + ("ALL",)][0]
        if not tot:
            line += f" | {b}: -"
            continue
        f = lambda act: 100 * stats[b][k + (act,)][0] / tot
        line += (f" | {b} n={tot:5d} F{f('FOLD'):3.0f} C{f('CHECK_CALL'):3.0f}"
                 f" Rh{f('RAISE_HALF'):3.0f} Rp{f('RAISE_POT'):3.0f}")
    print(line)

print("\n== Folds to a bet/raise that gave up the best final hand")
for st in STREETS[1:]:
    print(f"  {st:6s} " + "  ".join(
        f"{b}: {gave_up[b][st][1]}/{gave_up[b][st][0]} ({100 * gave_up[b][st][1] / max(1, gave_up[b][st][0]):.0f}%)" for b in "AB"))

print("\n== Unopened bets without the best final hand: n, and how often the other folded")
for st in STREETS[1:]:
    print(f"  {st:6s} " + "  ".join(
        f"{b}: {bluffs[b][st][0]} bets, folded {100 * bluffs[b][st][1] / max(1, bluffs[b][st][0]):.0f}%" for b in "AB"))

print("\n== Raise sizes (half / pot)")
for st in STREETS:
    print(f"  {st:8s} " + "  ".join(
        f"{b}: {sizes[b][(st, 'RAISE_HALF')]}/{sizes[b][(st, 'RAISE_POT')]}" for b in "AB"))
