# Experiment log

Every change to ShortStack's play is measured with a paired A/B against the
opponent pool before it is kept.

```bash
python -m sim.ab --cand "label:param=value,param2=value" --seeds 101 102 103 104
```

`sim/ab.py` plays the candidate and the baseline (both `BrainPlayer`, safety
wrapper included) against every pool bot on the same seeds, 1,000 duplicate
deals each. It prints both arms per opponent, the difference, and the pool
mean difference with two standard errors (spread of per-seed means, and the
per-deal paired differences). "field" is the pool without our own self-play
variants.

**Keep rule:** pool mean diff at least +0.05 bb/deal, more than about 2 SE from
zero, and no non-self opponent worse by more than 0.3 bb/deal. At least 8
seeds before keeping.

## Pool changes (November 2026)

| Bot | What it models |
|---|---|
| `mc_careful` | A careful MC-equity bot (equity vs one random hand, 32 to 48 `omaha_score` samples, fixed thresholds shifted by a live fold/raise model). Drains its bank. |
| `range_pro`, `range_aggro` | Fast range-aware bots (our vectorised equity, ranges from their opponent's bets this hand, balanced bluffs), standing in for the strongest teams |
| `barreler`, `barreler_half` | Bet 70 to 85% of the time when checked to, whatever they hold: punish over-folding |

The simulator now also charges 0.3 ms per decision for the judge's HTTP and
JSON overhead (measured on the real judge), so opponents drain their bank
at about the same point as they do through HTTP.

## Results

### Harness fix: deterministic timing (kept)

The first A/B run timed our bot with the wall clock, as production does.
Sample counts then depended on machine load, so two arms with *identical*
parameters drifted apart: the A/A control showed +1.44 bb/deal against
`maniac` and a pool mean of +0.047 (z = 1.0). On that noise
`thin_river_shift=0.20` looked like +0.145 (z = 3.6), which later vanished.

`sim.players.VirtualClock` now times our bot in the simulator: 0.1 ms per
timed call, 0.45 ms per Monte Carlo call plus 4.5 us per sample (measured
equity-call cost, padded to match full-match sample counts). Identical
parameters now give identical play. Batch 1's A/A arm: pool mean -0.007,
field +0.001 (what is left comes from opponents that time themselves on the
real clock: `agent`, and bots that drain their bank). Real timing is still
checked separately through the judge.

### Batch 1 (seeds 101-104, deterministic)

| Candidate | Pool diff (all) | Field diff | Notes | Verdict |
|---|---|---|---|---|
| A/A (no change) | -0.007 | +0.001 | noise floor | - |
| `thin_river_shift=0.20` | -0.006 | +0.009 | | reject |
| `thin_river_shift=0.20, thin_river_raise=1` | +0.011 | +0.039 | | not significant |
| `river_value_range=1` (value-bet vs learned calling range) | -0.025 | -0.051 | -0.47 vs calling station: the shrunk calling floor (prior 0.5) is far too tight for a station, so it stopped betting medium hands | reject |
| `river_bluff_adapt=1` (bluff air when measured river fold rate pays) | +0.011 | +0.015 | rarely triggers: few bots fold 33%+ to our river bets | not significant |
| `learn_postflop=1` | **+0.164** | **+0.146** | 23 of 31 non-zero opponents up; worst `adaptive_loose` -0.37 (se 0.31) | confirm on 8 seeds |
| `autopilot_streak=6, min_folds=3` | +0.001 | +0.009 | no earlier triggers that matter | reject |

### Batch 2: confirmation (seeds 105-112, fresh)

| Candidate | Pool diff (all) | Field diff | Worst field opp | Verdict |
|---|---|---|---|---|
| `learn_postflop=1` | **+0.144** (se 0.020-0.026, z 5.6) | **+0.097** (z 2.7) | `adaptive_loose` -0.29 | **KEEP** |
| `learn_postflop=1` + thin river 0.20 with raises | +0.150 | +0.106 | `adaptive_loose` -0.24 | not kept: +0.006 over `learn_postflop` alone is noise |
| `learn_postflop=1` + adaptive river bluffs | +0.164 | +0.089 | `adaptive_loose` -0.28 | not kept: no field gain over `learn_postflop` alone |

`learn_postflop` (the opponent's postflop bet range moves toward
1 - their aggression rate, then toward their showdown hands) was switched off
after an ablation against the old, weaker pool. Against the stronger pool it
wins broadly: `range_pro` +0.35, `mc_basic` +0.36, `barreler` +0.20, `mc_careful`
+0.11. It is now the default (`self_learnpost` in the pool became
`self_nolearnpost`).

### Final checks (learn_postflop on)

* `python -m pytest -q`: 56 passed.
* League (`python -m sim.league --focus agent --seeds 1 2 3`, real clock):
  69-25-2 overall, +2.27 bb/deal; against the 22 non-self bots 65 wins,
  1 chop (`range_pro`), +3.28 bb/deal. Both losses are self-play variants.
* Slow machine: `test_time_budget_holds_on_a_slow_machine` (every equity call
  twice as slow, a full half against an always-raise bot, real clock) passes.
* `./tools/check_build.sh`: passed, 0 MB added on top of the base image.

### Batch 3-5: reading always-bettors (idea from Drew's sdplo bot)

Drew's bot (`x_drew_real`, an EV maximiser over Bayesian opponent ranges)
beat the same 22-bot field by far more than we did against hyper-aggressive
bots (always_half +11.9 vs our +5.1, maniac +11.0 vs +6.5), though it lost
everywhere else and lost to us 8-0 in-process and 3-0 on the real judge.
`sim.probe` showed why: against always_half we folded 47% on the flop and
55% on the river, and a third of those folds gave up the best hand.
`opponent_aggression` floored any multi-street bettor at `agg_bet` (0.40)
and added 0.08 per earlier street bet, so a bot that bets every street with
random hands was read as a top-44% hand by the river.

| Candidate | Seeds | Pool diff (all) | Field diff | Notes | Verdict |
|---|---|---|---|---|---|
| floor = learned bet level, step x 2(1 - aggression) | 101-104 | +0.058 | +0.115 | +0.7 to +0.9 vs aggressive bots, but -0.35 to -0.41 vs every MC threshold bot: the learned floor reads selective bettors as too weak | reject |
| same, floor and step fade only above 50% aggression (`agg_prev_adapt=1`) | 101-104 | +0.117 | +0.179 | selective bettors unchanged to the chip | confirm |
| `agg_prev_adapt=1` | **105-112** | **+0.119** (z 7.0) | **+0.177** | always_half +1.46, maniac +0.78, barreler_half +0.65, always_pot +0.48, random +0.41; worst mc_drain -0.09 | **KEEP** |

### Drew's sdplo bot, measured (November 2026)

`x_drew_real` is github.com/burnerdrew2-prog/tamu-heads-up-bot at c011492
(Bayesian opponent ranges, EV over three raise sizes, load-scaled time guard).

| Measurement | ShortStack | Drew's bot |
|---|---|---|
| Head-to-head in-process, 8 seeds | **8-0-0, +1.85 bb/deal** | 0-0-8 |
| Head-to-head, real judge, fresh servers per half | **3 wins, 1 chop**: +1.22, +1.88, +1.38, +0.46 | ran out of time in 3 of 8 halves (41-173 calls skipped) |
| Same 22-bot field, 3 seeds each | **65-1-0, +3.28** (before `agg_prev_adapt`); **66-0-0, +3.67** after | 58-4-4, +3.31; loses to `range_pro` 3/3 |
| vs hyper-aggressive bots (always_half, maniac) | +5.1, +6.5 before; +7.0, +7.9 after | +11.9, +11.0 |
| vs MC-threshold bots (mc_basic, mc_careful, adaptive) | +3.1, +2.2, +3.1 | +1.2, +0.6, +1.8 |
| Thinking time per half, real judge | 3.9-5.3 s | 5.7-8.0 s |

The one transferable idea (read always-bettors as betting their range) is
`agg_prev_adapt` above. Against Drew's bot itself it is neutral (-0.04,
se 0.15, 8 seeds).

### Batch 6: thinking budget

| Candidate | Pool diff (all) | Field diff | Verdict |
|---|---|---|---|
| `logic_share=0.35` (from 0.45) | -0.245 | -0.297 | reject |
| `logic_share=0.30` | -0.387 | -0.472 | reject |

Samples are worth a lot, so 0.45 stays. It is not raised either: the time
bank assumes 0.6 ms of judge overhead per request, and a machine about 2x
slower than this laptop (about 1.2 ms per request) could empty the bank
at 0.55. Cheaper equity calls (0.35 ms of each call is the weight function,
not sampling) would buy samples without that risk.

### Slow-machine time guard (kept)

A real-clock half against an always-raising bot (the most decisions), with
every equity call slowed and the judge's unseen per-request overhead raised
to match (laptop: about 0.45 ms per request):

| Machine | Before: charged / bank empty | After: charged / bank empty |
|---|---|---|
| 1x (0.4 ms overhead) | 5.0 s / no | 5.0 s / no (identical play: scale 1.00) |
| 2x (0.9 ms) | 6.7 s / no | 6.6 s / no |
| 3x (1.35 ms) | 8.0 s / **yes** | 6.0 s / no |
| 4x (1.8 ms) | 8.0 s / **yes** | 5.8 s / no |

The fix (idea from Drew's bot): `Brain` times a fixed 400-sample equity call
(best of 5) at the start of each half and every 100 hands, on its own RNG.
The ratio to this laptop (1.25-1.5 ms; reference 1.6 ms) scales the assumed
per-request overhead and the cheap-fallback headroom, so a slow machine
thinks less instead of running out. Under the simulator's virtual clock the
probe is skipped, so A/B results are unaffected. Real judge vs Drew's bot
afterwards: 4.08 s of 8 s, as before.

### Faster equity engine (kept)

Profiling a 600-sample equity call showed work that was repeated or slower
than it needed to be:

| Change | Effect |
|---|---|
| Our own hand: best rank per board triple built once per hand (10 contiguous rows of the table), so each runout costs 10 lookups instead of 100 | about 0.6 us per sample saved on the flop and turn |
| River: the opponent's score comes from a 630-entry best-per-pair table for the fixed board | about 4x faster river calls |
| Range weights: made-hand strength from the same per-pair table, one argsort instead of two, flush draws by comparing only the suits that are live | about 2x cheaper weights |
| Card sampling: partial Fisher-Yates over all rows (argsort of random keys kept below 64 samples) | about 1.7x faster |

Given the same cards the results are bit-identical (checked over 800 random
spots). On our bot's recorded equity calls from full matches the new engine
takes 0.54-0.58x the time, so `sim.players.VirtualClock` moved from
0.45 ms + 4.5 us per sample to 0.32 ms + 2.5 us. The timing probe got
faster too (0.76x, interleaved), so `REF_PROBE_SECONDS` moved from 1.6 ms
to 1.2 ms (idle laptop: 1.07-1.26 ms, load scale 1.00-1.05). Real clock
afterwards: 4.6 s charged per half, 0 errors, as before.

### Batch 7: what the extra samples are worth (seeds 101-108)

| Candidate | Pool diff (all) | Field diff | Notes | Verdict |
|---|---|---|---|---|
| old engine cost (`vc_per_call=0.00045, vc_per_sample=4.5e-6`) | -0.035 | **-0.079** (z -2.2) | so the speedup is worth about +0.04 to +0.08 | speedup **KEPT** |
| `pot_exponent=0.667` (samples in proportion to pot^(2/3)) | +0.009 | -0.008 | | reject |
| `pot_exponent=0.667, mc_max_samples=3000` | -0.008 | -0.025 | | reject |
| `mc_max_samples=3000` | -0.010 | -0.004 | identical play against 26 of 33 bots: the 1,500 cap almost never binds | reject |

Extra samples have diminishing returns: cutting `logic_share` from 0.45 to
0.35 cost 0.25 bb/deal (batch 6), but 1.8x more samples on top of the
current budget adds only about 0.05.

### Drew's sdplo_v4, measured (November 2026)

Drew pushed sdplo_v4 (c0b0a6a) after the sdplo_v3 measurement above. Its
commit says it makes the same decisions as v3 whenever time is not short,
plus a fallback mode that uses the opponent model when the bank runs low.
ShortStack here is d424b0c (the options added since 00cc8c3 are all off
by default, so play is the same as 00cc8c3).

| Measurement | ShortStack | Drew's bot |
|---|---|---|
| vs **sdplo_v3** (c011492), in-process, seeds 1-8 | **8 wins**, +1.29 bb/deal (+0.92 to +1.78) | |
| vs **sdplo_v4**, in-process, seeds 1-8 | 0 wins, 5 chops, 3 losses, **-0.29**: +0.24, -0.67, -0.02, +0.20, +0.02, -0.93, -0.58, -0.59 | 6.5-7.6 s of 8 s, bank never empty |
| vs **sdplo_v4**, real judge, fresh servers per half, seeds 21-24 | **2 wins, 2 chops**, +0.55: +0.72, +0.58, +0.43, +0.47 | **bank empty in all 8 halves** (89-424 calls skipped) |
| Thinking time per half, real judge | 5.5-6.2 s, 0 errors | 8.0 s (wall 9.7-10.5 s) |

* The in-process runs were 8 parallel processes on a 16-core laptop.
  Both bots read the wall clock, so a single seed is noisy: seed 6 against
  v4 gave -0.93 and then +0.37 on a rerun.
* So v4 at full strength edges ShortStack, and sdplo_v3 was probably in
  its weak fallback mode for much of the earlier in-process run. The
  simulator charges 0.3 ms per request against about 0.45 ms on the real
  judge, so v4 keeps its bank in-process and empties it on the real judge.
* Our real-judge margin fell from +0.46 to +1.88 against v3 to +0.43 to
  +0.72 against v4, and two of four matches chopped. If the tournament
  machine is faster than this laptop, or Drew trims his time use, expect
  chops or narrow losses.
* On this laptop the judge cannot reach the bots through `localhost` (the
  name lookup takes longer than the 2 s health-check timeout). Use
  `--agent1 http://127.0.0.1:5008 --agent2 http://127.0.0.1:5009`.

### Batch 8: threshold screen (seeds 101-104, 21 strong opponents)

One change per arm against 21 opponents chosen for strength and variety
(range_pro, range_aggro, mc_careful, x_drew_real, the MC bots,
adaptive bots, barrelers, nit, maniac, guide_example, random and four self
variants). Columns: diff in bb/deal for the pool and the field, then
against the two strongest bots. `x_drew_real` results are noise here:
it times itself on the real clock, and with 15 workers sharing the CPU its
bank emptied in 4 of 8 base halves but rarely in the candidate arms, so
every arm showed -0.2 to -1.4 against it (about -0.03 on each pool mean).
It is measured through Docker instead, and left out of later batches. Most arms also sit about +0.1
above the base, which points to an unlucky base run; the confirmation
batch carries an A/A arm to measure this.

| Candidate | Pool | Field | range_pro | range_aggro | Next |
|---|---|---|---|---|---|
| `barrel_weight=0.4` | +0.184 | +0.222 | +0.011 | -0.124 | confirm |
| `post_pot_size_eq=0.70` | +0.123 | +0.128 | +0.172 | +0.106 | confirm |
| `sb_raise_pot_above=0.75` | +0.133 | +0.140 | -0.066 | +0.195 | confirm |
| `post_bet_eq=0.63` | +0.125 | +0.134 | -0.055 | -0.017 | confirm |
| `post_raise_eq=0.65` | +0.124 | +0.154 | -0.085 | -0.042 | confirm |
| `sb_raise_half_above=0.55` | +0.120 | +0.141 | +0.180 | -0.167 | within the base offset |
| `sb_raise_half_above=0.65`, `sb_fold_below=0.10`, `bb_raise_above=0.80`, `post_bet_eq=0.57` | +0.096 to +0.103 | | | | within the base offset |
| `adaptive_samples=1` (z 2 / z 1.5) | +0.059 / +0.065 | | -0.119 / -0.019 | -0.132 / -0.033 | reject |
| `pre_reraise_equity` 0.54 / 0.60, `pre_call_margin_oop` 0 / 0.06, `post_raise_eq=0.71`, `post_pot_size_eq=0.80`, `barrel_weight=0.8`, `bb_raise_above=0.60` | +0.01 to +0.07 | | | | reject |
| `river_value_range=1` with a 0.3 prior | **-0.198** | -0.246 | | | reject |
| `draw_raise=0.5` | **-0.175** | -0.213 | | | reject |
| `commit_shove_eq=0.50` | -0.102 | -0.131 | | | reject |

### Docker matches vs Drew's sdplo_v4 (tournament conditions)

The organizers suggested playing other teams' images. `tools/container_match.sh`
built both bots with the organizers' Dockerfile (ShortStack at 12ac2aa,
Drew's bot at c0b0a6a, sdplo_v4) and played each half in fresh containers
with 1 CPU, 4 GB and read-only files, the judge on a private Docker network.

| Seed | ShortStack bb/deal | 95% CI | Verdict | ShortStack time | Drew's bank |
|---|---|---|---|---|---|
| 11 | +1.23 | +0.89 to +1.56 | win | 5.6 / 5.5 s | empty, 663 / 665 calls skipped |
| 12 | +1.21 | +0.81 to +1.61 | win | 5.7 / 5.5 s | empty, 703 / 669 skipped |
| 13 | +0.73 | +0.20 to +1.25 | win | 5.5 / 6.4 s | empty, 667 / 170 skipped |
| 14 | **+0.17** | -0.41 to +0.74 | **chop** | 6.2 / 6.2 s | empty only at the end, 22 / 19 skipped |

Three wins and a chop, with 0 errors. The wins come largely from Drew's
bot emptying its bank a third of the way through the half on 1 CPU; when it
kept its bank (seed 14) the match was close to even. On a faster
tournament machine that is the match to expect.

Two trivial bots (calling stations) in the same setup were charged
0.52-0.65 ms per request, so the time bank's 0.6 ms overhead assumption
holds in containers. ShortStack's 5.5-6.4 s comes from the cheap 40-sample
fallback, which runs until about 2.5 s of the bank is left by design.

### Batch 9: per-street bet levels (idea from the Drew duplicate diff)

Diffing the two halves deal by deal (same cards, seats swapped) against
sdplo_v4, the biggest loss is deals where ShortStack folds to a flop or
turn bet with both hands while Drew's bot holding the same cards plays on
(about -4.2 bb per such deal). ShortStack folded to 73-79% of bets, Drew's
bot to 44-50%. Drew's single bets, measured on all 8,000 hands of seeds
1-4 (made-hand strength vs random hands):

| Street | Drew bets first-in | 20th pct of bet strength | Bets below 0.40 | Level ShortStack used (learned) |
|---|---|---|---|---|
| flop | 39% | 0.22 | 31% | 0.29 |
| turn | 41% (barrel 60%) | 0.18 | 38% | 0.32 |
| river | 28% | **0.62** | 5% | 0.33 |

One learned level for all streets was too tight on the flop and turn and
far too loose on the river. `street_levels=1` refines the all-streets
showdown estimate with that street's own showdowns.

| Candidate | Pool (seeds 101-104) | Field | range_pro | range_aggro | mc_careful | vs `x_drew_fast` (seeds 1-8) | Verdict |
|---|---|---|---|---|---|---|---|
| `street_levels=1` | **+0.108** (z 3.3) | +0.110 | +0.340 | +0.216 | -0.274 | +0.230 (se 0.124) | **KEEP** |
| `barrel_weight=0.3` | +0.152 (z 4.4) | +0.259 | -0.156 | -0.102 | +0.090 | +0.017 (se 0.241) | not kept: hurts the closest bots |
| both | +0.207 (z 5.9) | +0.323 | +0.128 | +0.016 | +0.177 | -0.138 (se 0.082) | not kept |

Results against Drew's bot vary a lot because it reads the wall clock: the
base arm scored -0.85 and -0.71 on the same seeds. `x_drew_fast` beats
ShortStack by about 0.7-0.85 bb/deal in-process, so a Drew's bot that keeps
its bank remains the hardest opponent.

### Batch 10: wild opening (image play)

Idea: play the first hands of a half at random (call or raise, never fold)
so a learning opponent starts the half reading us as loose, then play
normally. `wild_hands` = how many hands, `wild_temp` = chance per decision.
Pool here = range_pro, range_aggro, mc_careful, adaptive, adaptive_loose,
mc_basic, barreler, self_static, seeds 101-104; Drew = `x_drew_fast`,
seeds 1-8.

| Candidate | Pool | range_pro | range_aggro | vs `x_drew_fast` |
|---|---|---|---|---|
| 50 hands, 0.5 | **-0.402** (z -4.9) | -0.430 | -0.355 | **+0.379** (se 0.109) |
| 50 hands, 1.0 | -0.497 | -0.513 | -0.977 | |
| 20 hands, 0.5 | -0.026 | -0.198 | -0.265 | +0.049 (se 0.130) |
| 50 hands, 0.2 | -0.143 | -0.267 | -0.112 | +0.339 (se 0.119) |

It throws Drew's Bayesian model off (his ranges for us stay too wide
for the rest of the half), but every dose costs about as much against
range_pro, and even the adaptive bots it is meant to fool beat it. It
also only pays when Drew's bot keeps its bank; when it empties its bank
(Docker on 1 CPU) the wild hands are pure cost. Left off (the default).
Worth a recheck with more Drew seeds if a fast tournament machine is
confirmed.

### Batch 8 confirmation: `post_pot_size_eq=0.70` (seeds 105-108, whole pool)

| Candidate | Pool | Field | range_pro | range_aggro | mc_careful | Worst field | Verdict |
|---|---|---|---|---|---|---|---|
| `post_pot_size_eq=0.70` | +0.018 (z 0.5) | +0.021 | -0.200 | -0.183 | +0.219 | mc_loose -0.673 | **reject** |

The screen's +0.11 to +0.17 against the two strongest bots did not
repeat on fresh seeds; it was most likely the unlucky base run batch 8
suspected. Not run against Drew's bot, since it already fails on the
closest pool bots.

### Batch 11: batch 8 finalists and river ideas (seeds 113-120, before `street_levels`)

27 opponents (the pool without `x_drew_real`, `agent` and six self
variants), 8 fresh seeds, plus an **A/A arm** with identical parameters.
The A/A arm came out -0.054 (z -7.4): against bots that read the real
clock the base itself moved by up to 0.6 bb/deal between two runs
(`mc_careful` -0.62, `mc_basic` -0.57). The paired
standard errors do not see this, so pool means against those bots are not
trustworthy under a loaded CPU. The A/A arm's diff was exactly 0 against
16 opponents (the baselines, `nit`, `maniac`, `weak_tight`,
`guide_example`, `checkfold`, `mc_loose`, `adaptive`, `barreler_half` and
the four self variants), so candidates are scored on those
("deterministic"), with the noisier strong bots alongside.

| Candidate | Deterministic 16 | Self variants | range_pro | range_aggro | Verdict |
|---|---|---|---|---|---|
| A/A | 0.000 | 0.000 | +0.042 | -0.022 | noise floor |
| `river_bluff_adapt=1, river_bluff_min_obs=6` | **+0.062** (se 0.012) | **+0.195** | **+0.307** | **+0.232** | **keep** (re-checked on the new base, below) |
| `river_bluff_adapt=1` (12 observations) | +0.014 | +0.047 | +0.156 | +0.090 | weaker than 6 |
| `barrel_weight=0.4` | +0.136 | -0.054 | -0.216 | +0.178 | reject: gains on weak bots only |
| `barrel_weight=0.4, post_pot_size_eq=0.70` | +0.150 | -0.014 | +0.025 | +0.105 | reject: same pattern |
| `post_call_margin=-0.02` | +0.044 | -0.100 | -0.231 | +0.103 | reject |
| `post_bet_eq=0.63` | +0.021 | +0.006 | -0.144 | +0.161 | reject |
| `agg_bet=0.35` | +0.021 | -0.020 | -0.006 | +0.120 | reject |
| `river_bluff_freq=0.12` | -0.021 | -0.047 | -0.035 | +0.157 | reject |
| `post_pot_size_eq=0.70` | -0.010 | -0.084 | -0.029 | +0.167 | reject |
| `sb_raise_pot_above=0.75` | -0.051 | -0.051 | -0.072 | +0.193 | reject |
| `post_raise_eq=0.65` | -0.113 | -0.213 | -0.037 | +0.422 | reject |

Adaptive river bluffs answer the leak `sim.probe` showed: range_pro folds
77% of the time to our river bets, yet ShortStack bluffed almost never
(9 of 257 folds). The rule only bluffs air when an opponent's measured fold
rate to that bet size pays for it, so stations switch it off by themselves.
Needing 6 observed river bets per size instead of 12 lets it start early
enough in the half to matter. It gains most against the strongest bots,
which is where matches are close.

### Batch 12: adaptive river bluffs on the `street_levels` base (seeds 121-128)

Re-run after `street_levels=1` became the default, against 21 opponents
including `x_drew_fast` (Drew's bot with a full time bank), with an A/A
arm. With 840 matches the CPU was less loaded and only `x_drew_fast`
and `mc_careful` moved in the A/A arm (+0.12, +0.05).

| Candidate | Deterministic 18 | Self variants | range_pro | range_aggro | x_drew_fast | Worst det |
|---|---|---|---|---|---|---|
| A/A | 0.000 | 0.000 | 0.000 | 0.000 | +0.118 (se 0.137) | 0.000 |
| `river_bluff_min_obs=6` | +0.055 (se 0.011) | +0.233 | +0.169 | +0.010 | +0.092 | -0.119 |
| **`river_bluff_min_obs=4`** | **+0.075** (se 0.013) | **+0.282** | **+0.214** | **+0.153** | +0.128 | -0.143 |
| `min_obs=6, margin=0.02` | +0.067 (se 0.012) | +0.232 | +0.307 | +0.015 | +0.084 | -0.035 |

(all with `river_bluff_adapt=1`). **Kept: `river_bluff_adapt=1`,
`river_bluff_min_obs=4`**, the best against the strongest bots. Against
`x_drew_fast` every arm is within the A/A noise.

The base lost to `x_drew_fast` by **-1.01 bb/deal** on these seeds: a Drew's
bot that keeps its bank is the match ShortStack would lose.

### Batch 13: minimum defense against frequent bettors (seeds 131-138)

`sim.probe` against `x_drew_fast` (4 seeds): it bets most flops (we faced
5,535 flop bets in 8,000 hands), we fold 68% of them, and a third of those
folds gave up the best hand (about 10,900 bb of pots). `defend_gain` lowers
the call threshold while our fold rate to their first bet on a street is
above `defend_target`, against bots with postflop aggression of at least
0.40. 22 opponents, A/A arm; only `x_drew_fast` (+0.18) moved in the A/A arm.

| Candidate | Deterministic 20 | Self variants | range_aggro | barreler | x_drew_fast | Worst det |
|---|---|---|---|---|---|---|
| A/A | 0.000 | 0.000 | 0.000 | 0.000 | +0.183 (se 0.112) | 0.000 |
| **`defend_gain=0.3`** | **+0.087** (se 0.029) | +0.052 | +0.114 | -0.098 | -0.131 (se 0.142) | always_half -0.146 |
| `defend_gain=0.5` | +0.052 | -0.022 | +0.190 | -0.148 | +0.008 | mc_loose -0.191 |
| `0.5, target 0.50` | +0.061 | +0.024 | +0.088 | -0.161 | -0.009 | barreler -0.161 |
| `0.5` with the river | +0.088 | +0.044 | +0.177 | -0.166 | -0.015 | barreler -0.166 |
| `0.8, cap 0.15` | +0.047 | +0.044 | +0.176 | -0.086 | +0.006 | mc_loose -0.414 |

range_pro is unchanged in every arm: its aggression is under 0.40, so the
rule never fires. **Kept `defend_gain=0.3`**: it passes the keep rule
(+0.087, z 3, no opponent worse than -0.15) and helps range_aggro and the
self variants. It does **not** fix the match against Drew's bot with a full
time bank: every arm is within that bot's A/A noise, and the base lost to
it by -0.86 bb/deal on these seeds.

### Final Docker matches vs Drew's sdplo_v4 and sdplo_v5 (build 33977a2)

The final build (river bluffs, wider defense and per-street levels on)
against both of Drew's latest versions, same container setup and seeds as
the first Docker run. This time Drew's bot kept its time bank in every
half (6.6-7.5 s of 8 s), so these are full-strength matches.

| Seed | vs sdplo_v5 (9f0857d) | vs sdplo_v4 (c0b0a6a) | Earlier build 12ac2aa vs v4 |
|---|---|---|---|
| 11 | +0.58 chop (-0.01 to +1.17) | **+0.63 win** (+0.07 to +1.19) | +1.23 win (Drew's bank empty) |
| 12 | +0.12 chop | 0.00 chop | +1.21 win (bank empty) |
| 13 | +0.10 chop | +0.12 chop | +0.73 win (bank empty) |
| 14 | **+0.63 win** (+0.02 to +1.23) | +0.36 chop | +0.17 chop (bank kept) |

2 wins and 6 chops, every margin zero or positive (mean +0.32 bb/deal),
0 errors, ShortStack at 5.3-5.9 s of 8 s. Seed 14 vs v4, the one match
where Drew's bot kept its bank both times, went from +0.17 to +0.36.
`x_drew_fast` (-1.0 in-process) overstates Drew's bot: it gets 3x the
thinking time it actually has on 1 CPU.

### Docker match vs CsaBest's PLO5-MCCFR (build 33977a2)

Another team's image, `fjdanisaf/plo5-mccfr:latest` (participant CsaBest),
pulled from Docker Hub; no public source repo was found. The image holds an
MCCFR blueprint over bucketed hands (fold, call, half-pot, pot) plus an
opponent model that switches to a Restricted-Nash-Response counter-strategy
once it is 90% sure which of its trained archetypes it faces (40+ actions).
Same container setup and seeds as the Drew runs.

| Seed | ShortStack bb/deal | 95% CI | Verdict |
|---|---|---|---|
| 11 | **-1.00** | -1.61 to -0.39 | loss |
| 12 | **-0.66** | -1.30 to -0.01 | loss |
| 13 | **-0.58** | -1.14 to -0.02 | loss |
| 14 | **-1.09** | -1.68 to -0.49 | loss |

Four losses (mean -0.83 bb/deal), 0 errors. Time is not the cause:
ShortStack used 6.0-6.6 s of 8 s, PLO5-MCCFR only 3.4-3.8 s. It is the
first container opponent to beat ShortStack, and by more than Drew's bot
ever did.

A second run with hand logs (`LOGS=1 tools/container_match.sh`, then `tools/dup_diff.py`) gave
-0.61, -1.32, -0.62 and -1.13 (two losses, two chops, mean -0.92). Diffing
its halves deal by deal: each deal's paired result is ShortStack's net with
a set of cards minus PLO5-MCCFR's net with the same cards, so each deal is
charged to the first decision where the two halves differ, where both bots
faced the same history with the same cards.

| First divergence | Deals | bb/deal | Avg per deal |
|---|---|---|---|
| SB first-in: ShortStack limps, PLO5 raises half-pot | 1498 | **-0.415** | -1.11 bb |
| BB vs SB raise: ShortStack calls, PLO5 pot 3-bets | 111 | -0.089 | -3.20 bb |
| Flop, checked to in position: ShortStack checks, PLO5 bets | 165 | -0.074 | -1.79 bb |
| SB first-in: ShortStack pot-raises, PLO5 raises half-pot | 765 | -0.054 | -0.28 bb |
| Flop first to act: ShortStack bets half-pot, PLO5 checks | 129 | -0.054 | -1.67 bb |

By street of first divergence: preflop -0.71, flop -0.19, turn -0.02,
river 0.00. Charging a deal to its first difference also charges the play
that follows, so the preflop figure includes the postflop hands that the
preflop choice leads to.

| | ShortStack | PLO5-MCCFR |
|---|---|---|
| SB first-in: fold / limp / raise | 6 / 54 / 40% | 13 / 11 / 75% (almost all half-pot) |
| Raise over a limp | 26% | 47% |
| Fold to a flop / turn / river bet | 69 / 70 / 88% | 43 / 45 / 53% |
| Those folds that gave up the best final hand (flop / turn / river) | 37 / 31 / 27% | 17 / 12 / 10% |
| Bets without the best hand that got a fold (flop / turn / river) | 23 / 19 / 20% | 65 / 65 / 81% |

Two leaks. Preflop, ShortStack limps the small blind more than half the
time where PLO5-MCCFR opens with a half-pot raise, and it then calls 86%
of raises and gives the pot up postflop. Postflop it is the Drew problem
again, only bigger: ShortStack folds 69-88% to bets, so PLO5-MCCFR's bets
without the best hand take the pot 65-81% of the time. ShortStack loses
2.4 bb/deal in hands it folds after the flop and wins 1.3 in hands
PLO5-MCCFR folds.

### Docker match vs quad-j's jish_4 (build 33977a2)

`ghcr.io/650joshlee/quad-j-jish:jish_4` (source:
github.com/650JoshLee/quad-j-jish), same setup and seeds. ShortStack lost
all four: -1.55, -1.84, -2.21, -2.04 (mean -1.91); a logged rerun gave
-2.32, -1.24, -1.91, -1.47 (mean -1.73). 0 errors; both bots used 6-7 s.

jish_4 is an equity bot like ours, but it reads every action through how
often that opponent takes it in that exact spot (a bet made 40% of the
time means the top ~40%), pot-raises the small blind with any hand above
48% equity vs random, and bets 98% of flops when nobody has bet.

| | ShortStack | jish_4 |
|---|---|---|
| SB first-in: fold / limp / raise | 8 / 53 / 39% | 3 / 36 / 61% (all pot) |
| Bet when nobody has bet, flop / turn / river | 23 / 35 / 37% | 98 / 56 / 68% |
| Fold to a flop / turn / river bet | 66 / 41 / 56% | 48 / 70 / 70% |
| Those folds that gave up the best final hand | 37 / 33 / 41% | 10 / 11 / 12% |

The diff charges -1.18 bb/deal to preflop (limping where it pot-raises:
-0.61; half-raising where it pot-raises: -0.46) and -0.53 to the flop.
Hands ShortStack folds on the flop cost -1.99 bb/deal.

Our own profiler made it worse: jish_4's postflop aggression (0.80) puts
it in the `maniac` profile 98% of the half, which drops our bluffs and
raises the bar to bet, while jish_4 folds to our bets 30-55% of the time.

### A sim loop against the real bots

Both bots' code runs in-process (`PLO5_PATH`, `JISH_PATH` in
`sim/pool.py`; PLO5-MCCFR copied out of its image, its C core needs
Linux, so `sim.ab` runs inside the jish_4 image). A match takes ~19 s
instead of ~70 s. ShortStack's baseline there: -1.44 vs jish_4 (Docker
-1.7 to -1.9), -0.3 to -0.6 vs PLO5-MCCFR (Docker -0.8 to -0.9).

**Noise.** PLO5-MCCFR, jish_4 and Drew's bot size their thinking by the
wall clock, so the same match differs between runs: an A/A arm (identical
play) measured +0.29 vs PLO5-MCCFR and -0.32 vs Drew's bot in one batch.
The cached baseline is useless for them (`--no-cache` always), and only
differences above ~0.3 mean anything against those two. jish_4 is close
to deterministic in-process (A/A within 0.1).

Running five container matches at once on the 16-CPU Docker VM emptied
ShortStack's time bank in several halves (up to 76 decisions skipped):
two at a time is the limit for honest container timing.

**What PLO5-MCCFR is.** An MCCFR blueprint (fold, call, half, pot) over
hand buckets, plus a model that switches to a trained counter-strategy
when the opponent fits one of seven simple archetypes (station,
loose-passive, over-folder, maniac, always-pot, always-half, random)
with 90% confidence and passes an absolute fit test. ShortStack fits
none, so it plays the blueprint against us.

Sim A/B, seeds 101-116 (diff vs current defaults, bb/deal):

| Candidate | jish_4 | PLO5-MCCFR | Notes |
|---|---|---|---|
| `freq_ranges=1` | -0.05 | -0.02 | neutral alone |
| `defend_*` wider (agg 0, gain 0.6, cap 0.15, river) | -0.20 | -0.09 | calling more loses to jish_4 |
| `sb_raise_half_above=0.35` | -0.06 | -0.14 | wider half-pot opens: no |
| `sb_raise_pot_above=0.40` | 0.00 | +0.16 | |
| `post_bet_eq=0.52, semi_bluff_freq=0.8` | +0.16 | noise | |
| `exploit=0` | +0.23 to +0.29 | none (profile stays default) | |
| combo: pot opens 0.40 + bet 0.52 + semi 0.8 + `freq_ranges` | +0.21 to +0.39 | noise | |
| combo + `exploit=0` | **+0.78 to +0.95** (3 runs) | noise | |
| combo + `maniac_max_ftb=0.30` | **+0.86** | noise | keeps the maniac mode for real maniacs |

`maniac_max_ftb` calls an opponent a maniac only when its fold-to-bet is
also low. Measured by our model: true maniacs and always-bettors stay
below 0.20, barrelers below 0.32, jish_4 0.27-0.52. In the whole pool
(seeds 101-104) combo + `maniac_max_ftb=0.30` gains on every close
opponent (range_pro +0.43, range_aggro +0.24, mc_careful +0.50, mc_drain
+0.37, self-variants +0.2-0.5) and gives up chips only against bots it
still beats by +2.9 to +8.7 (maniac -0.92, always-half -1.22, random
-1.40, barreler -0.52): no match points change. With `exploit=0` instead
the maniac loss doubles (-1.86).

### Docker validation of the new defaults (seeds 11-18)

Old defaults vs the combo (`sb_raise_pot_above=0.40, post_bet_eq=0.52,
semi_bluff_freq=0.80, freq_ranges=1, maniac_max_ftb=0.30`), both arms
played side by side (two matches at a time, the same load), 1 CPU each:

| Opponent | Old bb/deal | New bb/deal | Diff (se) | Points of 8, old -> new |
|---|---|---|---|---|
| Drew's sdplo_v5 | +0.25 | **+0.71** | +0.46 (0.13) | 4.5 -> 6.5 |
| Drew's sdplo_v4 | +0.16 | **+0.78** | +0.62 (0.14) | 4.0 -> 7.0 |
| CsaBest's PLO5-MCCFR | -0.90 | **-0.54** | +0.36 (0.14) | 1.0 -> 3.0 |
| quad-j's jish_4 | -1.95 | **-0.87** | +1.08 (0.17) | 0.0 -> 2.0 |

9.5 -> 18.5 points over the 32 matches. Every empty time bank in these
runs was Drew's bot; ShortStack used 5.8-6.3 s of 8 s with 0 errors.
These are now the defaults.

Cycle 1 in the sim on top of the new defaults (seeds 101-116; A/A
moved up to 0.09): re-raising more preflop (`pre_reraise_equity=0.54`),
raising bets more (`post_raise_eq=0.64`), minimum defense against
PLO5-MCCFR (`defend_agg=0.30`), pot opens from 0.30, betting from 0.50
with every draw. None moved any opponent by more than noise; the
parameters are at a local optimum and the next gains need new behaviour.

Diffing the new defaults' Docker logs (8 seeds each): vs jish_4 (-0.87)
the biggest first divergence is the big blind checking the flop where
jish_4 leads (n=2427, -0.58 bb/deal), and hands we fold after the flop
still cost -3.8 bb/deal (+1.9 back from its folds). Vs PLO5-MCCFR
(-0.54) it is preflop: in the big blind we call 90% of raises (it folds
49%), then fold 72% to flop bets. Both diffs say the same thing: we call
too much before the flop and fold too much after it.

Cycle 1, structural (seeds 101-116, A/A within 0.07):

| Candidate | jish_4 | PLO5 | Drew | Others |
|---|---|---|---|---|
| `raise_bluff_adapt=1` (new: raise a flop/turn bet we would fold when their measured fold-to-raise pays) | **-0.42** | -0.18 | -0.20 | barreler +0.18 |
| same, looser (min eq 0.10, 3 obs) | -0.41 | -0.19 | -0.15 | |
| `pre_call_margin_oop=0.06` | +0.15 | -0.11 | -0.28 | adaptive -0.14 |
| `pre_call_margin_oop=0.10` | +0.33 | -0.06 | -0.14 | adaptive -0.15 |

The raise-bluff backfires: jish_4 discounts the strength of an action
the more often its opponent takes it, so once we raise often it calls
and re-raises. Left off.

Cycle 2 (seeds 101-116). The high flop calling bar against jish_4 comes
from `call_odds`: against 0.80 aggression, `barrel_weight` puts the flop
price at ~96% of the way to all-in odds. Lowering it was the obvious
test:

| Candidate | jish_4 | PLO5 | Drew | Others |
|---|---|---|---|---|
| A/A | -0.04 | -0.08 | -0.22 | |
| `barrel_weight=0.4` | -0.12 | -0.06 | -0.06 | |
| `barrel_weight=0.2` | -0.18 | 0.00 | +0.02 | adaptive -0.36 |
| `barrel_weight=0.0` | **-0.61** | -0.06 | -0.19 | adaptive -0.33 |
| `pre_call_margin_oop=0.10` | +0.22 | +0.01 | -0.25 | adaptive -0.15 |
| `post_pot_size_eq=0.85` | -0.15 | -0.06 | -0.14 | |
| `post_pot_size_eq=0.65` | +0.12 | -0.03 | -0.16 | mc_careful +0.16, barreler -0.19 |

jish_4 really does keep betting, so the barrel price is right: folding
the flop is cheaper than calling and folding the turn. The tighter big
blind (+0.33 and +0.22 vs jish_4 in two runs) went to Docker.

Docker, seeds 11-18, new defaults vs `pre_call_margin_oop=0.10`:

| Opponent | Defaults | 0.10 | Diff (se) | Points of 8 |
|---|---|---|---|---|
| jish_4 | -1.06 | -0.62 | +0.43 (0.20) | 1.0 -> 2.5 |
| PLO5-MCCFR | -0.61 | -0.39 | +0.22 (0.08) | 2.5 -> 4.0 |
| Drew's sdplo_v5 | +0.70 | +0.54 | -0.16 (0.10) | 6.0 -> 5.0 |
| Drew's sdplo_v4 | +0.73 | +0.57 | -0.16 (0.05) | 6.5 -> 5.5 |

+1 point net, but it trades margin against a bot we beat for less loss
against the two that beat us. What separates them: when we bet the flop,
Drew's bots fold 48%, PLO5-MCCFR 38%, jish_4 18% (and jish_4 now raises
35% of our flop bets: it adapted to the extra betting). A big-blind call
only pays when we can win after the flop, so `bb_call_adapt` adds
`bb_call_adapt x (bb_call_ref - their flop fold rate)` to the
out-of-position margin, capped at `bb_call_cap`.

Sim (seeds 101-116): `bb_call_adapt=0.5` jish_4 +0.35, PLO5 +0.08, Drew
-0.04, but range_pro -0.16, range_aggro -0.15 (both deterministic, so
real; still won by +1.3 and +1.7). Docker, seeds 11-18:

| Opponent | Defaults | `bb_call_adapt=0.5` | Diff (se) | Points of 8 |
|---|---|---|---|---|
| jish_4 | -1.03 | -0.60 | +0.43 (0.09) | 0.0 -> 2.0 |
| PLO5-MCCFR | -0.61 | -0.67 | -0.06 (0.11) | 3.0 -> 2.0 |
| Drew's sdplo_v5 | +0.67 | +0.53 | -0.14 (0.09) | 6.5 -> 5.0 |
| Drew's sdplo_v4 | +0.66 | +0.62 | -0.04 (0.11) | 6.0 -> 6.0 |

Turning the means into expected match points (95% CI half-width 0.5,
so se ~0.255 per match), the adaptive margin is worth ~0.0 points over
these four opponents and the fixed 0.10 ~+0.1: both swap likely wins
against Drew-level bots for fewer losses against the top two. Neither
is a default; both stay available. Across the three Docker runs of the
new defaults the results held steady: jish_4 -0.87 / -1.06 / -1.03,
PLO5-MCCFR -0.54 / -0.61 / -0.61, Drew +0.67 to +0.78.

### Against maniacs, and a league check (build bfa5d5f)

The pool league in the Linux image (seeds 1-3, real clock, so margins
run lower than on the Windows host) found one cost of the new defaults:
betting from 52% equity bets medium hands into bots that raise
everything, and they get raised off them (always-half +3.56 -> +2.25,
one chop). In the maniac profile, `maniac_bet_eq=0.68` puts the bar back
up and lets them bluff into us. Sim, seeds 101-108: barreler +0.41,
random +0.34, maniac +0.17, always-pot +0.14; jish_4 -0.02, the range
bots 0.00. Kept.

| League, Linux image, seeds 1-3 | Old defaults | New defaults |
|---|---|---|
| 22 non-self pool bots (66 matches) | 62 W, 4 chops | **65 W, 1 chop** |
| range_pro / range_aggro | +0.60 / +0.68 | **+1.08 / +1.00** (all wins) |

The one chop is variance against always-pot (+1.43, CI -0.24 to +3.09).
`tools/check_build.sh` passes on this build (14 MB over the base).

### Field scan: 19 other teams' bots (build 7ab25b6)

Each team's public repo (latest `main`), played through `judge_engine.py`
over HTTP on the Windows host: fresh servers for both bots every half,
seeds 1-3, 1,000 deals a half, six matches at once. P(win/chop/loss) is
for one tournament match, from the three-seed mean and the per-match
stderr (predicted mean ~ N(m, s² (1 + 1/3)), verdict by the 95% CI).
We had 0 errors and used at most 5.7 s of the bank in any half.

| Opponent (repo) | W/C/L | Mean | Per seed | P(win) | P(chop) | P(loss) | Exp. pts |
|---|---|---|---|---|---|---|---|
| EthereumEthan/plo-heads-up-agent | C L L | **-0.74** | +0.19, -1.07, -1.35 | 0% | 48% | 52% | 0.24 |
| LaserRyan/Heads-Up-Poker | C C L | **-0.52** | -0.47, -0.23, -0.85 | 0% | 62% | 38% | 0.31 |
| The007Programmer/AEY-TDatathon (FiWBot) | C C C | -0.39 | -0.45, -0.06, -0.67 | 1% | 79% | 20% | 0.40 |
| SahithReddy-GitHub/poker-bot-tamu-datathon | C C C | -0.37 | -0.34, -0.44, -0.33 | 0% | 78% | 21% | 0.40 |
| aurora-quantitative-group/Aurora-Poker-Bot | C C C | -0.36 | -0.53, -0.06, -0.49 | 1% | 79% | 21% | 0.40 |
| Aditi6301/rangehunter | C C C | -0.17 | +0.14, -0.46, -0.19 | 2% | 90% | 8% | 0.47 |
| karammasad/pokerMAKK | C C C | -0.01 | +0.39, -0.43, +0.01 | 4% | 91% | 5% | 0.50 |
| ghodkeadityarao-tamu/twostack-poker-bot | C C C | +0.08 | +0.24, -0.34, +0.34 | 7% | 90% | 3% | 0.52 |
| conorwang8/big-cheese-poker-bot | C C C | +0.45 | +0.59, +0.27, +0.50 | 24% | 75% | 0% | 0.62 |
| andrewv426/timecasters-pokerbot | W C C | +0.62 | +1.23, +0.26, +0.36 | 42% | 58% | 0% | 0.71 |
| shaswat-singh23/datathon-poker | W C W | +0.85 | +0.73, +0.46, +1.34 | 71% | 29% | 0% | 0.85 |
| DiegoAC06/heads-up-green-fn | W W W | +0.93 | +1.42, +0.78, +0.58 | 86% | 14% | 0% | 0.93 |
| Dhanush006/ssd-heads-up-poker | W W W | +1.19 | +1.36, +0.94, +1.28 | 89% | 11% | 0% | 0.94 |
| dimi1729/2026_datathon_poker | W W W | +1.10 | +1.34, +0.92, +1.05 | 95% | 5% | 0% | 0.97 |
| awojinrin/xplore-heads-up-poker-bot | W W W | +1.45 | +1.81, +1.34, +1.20 | 99% | 1% | 0% | 1.00 |
| AllenChirayil/stallion-poker-bot | W W W | +1.46 | +1.47, +0.92, +1.99 | 100% | 0% | 0% | 1.00 |
| Sploofie/f26-datathon-poker-bot (starter bot) | W W W | +1.50 | +1.50, +1.50, +1.50 | 100% | 0% | 0% | 1.00 |
| abzf0/heads-up-dt26 | W W W | +1.93 | +2.56, +1.66, +1.56 | 100% | 0% | 0% | 1.00 |
| shriharish1310/tamu-datathon-poker-bot | W W W | +2.17 | +2.37, +1.92, +2.23 | 100% | 0% | 0% | 1.00 |

Expected total: **13.3 of 19 points** (31 W, 24 C, 3 L over 57 matches).
abzf0, stallion, shaswat, shriharish and plo-heads-up-agent (seed 1)
emptied their time banks in some halves with six matches sharing the
laptop, so those margins aren't tournament-exact. plo-heads-up-agent's
one non-negative seed was one of those, so it is likely a little
stronger than shown. None of these are confirmed in Docker yet; the five
negative ones are the ones worth confirming and diffing.

### Field scan, part 2: 17 more bots from the Devpost poker track

The repos linked from the Devpost submissions for the poker prize that
weren't in part 1 (six projects link no code and one repo is private), run
the same way. We had 0 errors and used at most 6.5 s of the bank.

| Opponent (repo) | W/C/L | Mean | Per seed | P(win) | P(chop) | P(loss) | Exp. pts |
|---|---|---|---|---|---|---|---|
| zuhairrr07/Poker-Bot | L L L | **-1.15** | -0.93, -0.82, -1.71 | 0% | 12% | 88% | 0.06 |
| Utsavdotcom/aura-farmer | C L L | **-1.01** | -0.40, -0.99, -1.65 | 0% | 19% | 81% | 0.09 |
| harishkumar123tamu/outliers | L L L | **-0.90** | -1.12, -0.90, -0.67 | 0% | 20% | 80% | 0.10 |
| dunlapjack/poker-bot | C C L | -0.37 | +0.12, -0.51, -0.71 | 0% | 77% | 22% | 0.39 |
| sereechid-ai/Polaris-Pokerbot | C C L | -0.36 | +0.21, -0.58, -0.72 | 0% | 77% | 22% | 0.39 |
| Prunuus/heads-up | C C C | -0.09 | -0.48, +0.01, +0.20 | 3% | 90% | 7% | 0.48 |
| malki-aal/heads-up-bundle | C C C | -0.04 | +0.35, -0.06, -0.41 | 4% | 91% | 6% | 0.49 |
| 100RandomHumans/Datathon-2026 | C C C | -0.02 | +0.61, -0.29, -0.38 | 4% | 91% | 5% | 0.50 |
| rayha-m/poker-bot | W W C | +0.39 | +0.46, +0.55, +0.15 | 47% | 53% | 0% | 0.74 |
| PayneAM/heads-up-bundle | W C W | +0.55 | +0.61, +0.35, +0.69 | 59% | 41% | 0% | 0.79 |
| jane-vo/tamu-datathon26 | W C W | +0.89 | +1.07, +0.74, +0.84 | 59% | 41% | 0% | 0.80 |
| AiWithAmman/heads-up-bundle-main | W W C | +1.19 | +1.86, +1.10, +0.59 | 60% | 40% | 0% | 0.80 |
| khoahonguyen0210/YAK-poker-bot | W C C | +0.71 | +1.83, +0.48, -0.19 | 71% | 29% | 0% | 0.86 |
| AdityaVSM/heads-up-bundle | W W W | +2.10 | +2.25, +2.12, +1.93 | 100% | 0% | 0% | 1.00 |
| Juan-Sett/HeadsUpBot | W W W | +2.12 | +1.31, +1.86, +3.19 | 100% | 0% | 0% | 1.00 |
| RedRojoaka/datathon_2026 | W W W | +2.16 | +2.42, +2.18, +1.88 | 100% | 0% | 0% | 1.00 |
| Nave3425/poker-bot | W W W | +8.19 | +8.52, +7.94, +8.11 | 100% | 0% | 0% | 1.00 |

Expected total for part 2: **10.5 of 17 points** (23.8 of 36 over both
parts). Three bots here beat us outright in most matches (zuhairrr07,
aura-farmer, outliers, -0.9 to -1.15), more than any bot in part 1.
AdityaVSM, RedRojoaka and zuhairrr07 (seed 3) emptied their time banks
with six matches sharing the laptop. zuhairrr07 still won that seed.

### Tighter big-blind calls against the field (build 6a67512)

The field scan's losing and even bots are the kind that pay off when we
call too wide preflop and fold too much after the flop (range-weighted
Monte Carlo bots that size bets by our fold rate). Both tighter big-blind
options went back on, judged against the scan's seeds 1-3 with the same
runner (ports 7000+; the first attempt shared 6000-6011 with batch 2 and
forfeited, so it was thrown away).

| Batch 1, 10 closest bots | Mean bb/deal | Expected points |
|---|---|---|
| Defaults (scan) | -0.14 | 4.53 |
| `pre_call_margin_oop=0.10` | -0.03 | 4.90 |
| `bb_call_adapt=0.5` | -0.03 | 4.91 |

Per bot, 0.10 vs the scan: ethereumethan +0.13, LaserRyan +0.17, FiWBot
+0.44, sahith +0.17, aurora +0.33, rangehunter +0.02, pokerMAKK +0.13,
twostack +0.03, big-cheese -0.29, timecasters -0.03. The two options
tie, but 0.10 already had Docker gains against jish_4 and PLO5-MCCFR, so
it went to batch 2 (same seeds, 14 matches): +0.27 bb/deal on average
(zuhairrr07 +0.42/+0.35, outliers +0.40/+0.10, dunlapjack +0.72/+0.65,
Polaris +0.29/+0.54, malki-aal +0.95, Prunuus +0.16, rayha-m +0.12),
with aura-farmer the one consistent loser (-0.33/-0.17) and
100RandomHumans -0.45 in one seed. `pre_call_margin_oop=0.10` is now the
default. Docker, seed 11, same image with the old value passed in:

| Opponent | 0.03 (old) | 0.10 (new) | Diff |
|---|---|---|---|
| zuhairrr07/Poker-Bot | -1.23 (loss) | -0.99 (loss) | +0.24 |
| Utsavdotcom/aura-farmer | -0.93 (loss) | -0.55 (chop) | +0.38 |

0 errors, at most 5.6 s of the bank. One seed each, so more Docker seeds
are still worth running before calling these matchups settled.

## What to try next

Done since the last list: PLO5-MCCFR and jish_4 diffs and Docker
validation, `freq_ranges`, the maniac fold-rate condition, pot-size
small-blind opens, betting from 52%; tested and left off: raise-bluffs,
lower `barrel_weight`, tighter or adaptive big-blind calls, bet sizing.

* **jish_4 (-0.9 to -1.1) and PLO5-MCCFR (-0.5 to -0.6)** still win. Both
  diffs now say we call too wide in the big blind (we call 84-93% of
  small-blind raises; PLO5-MCCFR folds 50% there, jish_4 38%) and fold too
  much after the flop. Every fixed tightening so far trades margin
  against Drew-level bots for less loss against these two
  (`pre_call_margin_oop=0.10`, `bb_call_adapt=0.5`: ~0 to +0.1 expected
  points over the four). A real fix probably needs better postflop play
  in called pots, not a narrower range.
* jish_4 adapts to frequency: once we bet more it raised 35% of our flop
  bets and folded only 18%. Anything that exploits it by frequency gets
  read and countered within a half (raise-bluffs lost 0.42). Balance,
  not exploitation, is the lever against it.
* Wall-clock bots (PLO5-MCCFR, jish_4, Drew's) need `--no-cache` and an
  A/A arm in every sim batch, and Docker for any decision closer than
  ~0.3 bb/deal. Run at most two Docker matches at once.
* Make `adaptive_loose` stop losing to `learn_postflop` (the one consistent
  negative).
