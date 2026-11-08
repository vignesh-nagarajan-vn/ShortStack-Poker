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
| `brown` | Clone of BrownBallers' `strategy/` (equity vs one random hand, 32 to 48 `omaha_score` samples, fixed thresholds shifted by a live fold/raise model). Validated against the real code in-process: ShortStack +2.07 bb/deal vs the clone, +1.96 vs the real bot (3 seeds), and both drain their bank. |
| `range_pro`, `range_aggro` | Fast range-aware bots (our vectorised equity, ranges from their opponent's bets this hand, balanced bluffs), standing in for the strongest teams |
| `barreler`, `barreler_half` | Bet 70 to 85% of the time when checked to, whatever they hold: punish over-folding |
| `x_brown_real` | The real BrownBallers code, if a checkout sits next to this repo. Validation only, excluded from default runs |

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
wins broadly: `range_pro` +0.35, `mc_basic` +0.36, `barreler` +0.20, `brown`
+0.11. It is now the default (`self_learnpost` in the pool became
`self_nolearnpost`).

### Final checks (learn_postflop on)

* `python -m pytest -q`: 56 passed.
* League (`python -m sim.league --focus agent --seeds 1 2 3`, real clock):
  69-25-2 overall, +2.27 bb/deal; against the 22 non-self bots 65 wins,
  1 chop (`range_pro`), +3.28 bb/deal. Both losses are self-play variants.
* Real judge vs the real BrownBallers code, tournament-style (fresh servers
  each half): seed 11 +2.18 bb/deal (CI +1.53 to +2.83), seed 12 +2.37
  (CI +1.73 to +3.01). ShortStack 3.55-3.97 s of 8 s, 0 errors;
  BrownBallers emptied its bank in all four halves (251-336 calls skipped).
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
| vs MC-threshold bots (mc_basic, brown, adaptive) | +3.1, +2.2, +3.1 | +1.2, +0.6, +1.8 |
| Thinking time per half, real judge | 3.9-5.3 s | 5.7-8.0 s |

The one transferable idea (read always-bettors as betting their range) is
`agg_prev_adapt` above. Against Drew's bot itself it is neutral (-0.04,
se 0.15, 8 seeds), and +0.15 against the real BrownBallers.

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
(range_pro, range_aggro, brown, x_brown_real, x_drew_real, the MC bots,
adaptive bots, barrelers, nit, maniac, guide_example, random and four self
variants). Columns: diff in bb/deal for the pool and the field, then
against the three strongest bots. `x_drew_real` results are noise here:
it times itself on the real clock, and with 15 workers sharing the CPU its
bank emptied in 4 of 8 base halves but rarely in the candidate arms, so
every arm showed -0.2 to -1.4 against it (about -0.03 on each pool mean).
It is measured through Docker instead, and left out of later batches. Most arms also sit about +0.1
above the base, which points to an unlucky base run; the confirmation
batch carries an A/A arm to measure this.

| Candidate | Pool | Field | range_pro | range_aggro | x_brown_real | Next |
|---|---|---|---|---|---|---|
| `barrel_weight=0.4` | +0.184 | +0.222 | +0.011 | -0.124 | +0.021 | confirm |
| `post_pot_size_eq=0.70` | +0.123 | +0.128 | +0.172 | +0.106 | +0.133 | confirm |
| `sb_raise_pot_above=0.75` | +0.133 | +0.140 | -0.066 | +0.195 | +0.023 | confirm |
| `post_bet_eq=0.63` | +0.125 | +0.134 | -0.055 | -0.017 | -0.195 | confirm |
| `post_raise_eq=0.65` | +0.124 | +0.154 | -0.085 | -0.042 | -0.274 | confirm |
| `sb_raise_half_above=0.55` | +0.120 | +0.141 | +0.180 | -0.167 | +0.175 | within the base offset |
| `sb_raise_half_above=0.65`, `sb_fold_below=0.10`, `bb_raise_above=0.80`, `post_bet_eq=0.57` | +0.096 to +0.103 | | | | | within the base offset |
| `adaptive_samples=1` (z 2 / z 1.5) | +0.059 / +0.065 | | -0.119 / -0.019 | -0.132 / -0.033 | | reject |
| `pre_reraise_equity` 0.54 / 0.60, `pre_call_margin_oop` 0 / 0.06, `post_raise_eq=0.71`, `post_pot_size_eq=0.80`, `barrel_weight=0.8`, `bb_raise_above=0.60` | +0.01 to +0.07 | | | | | reject |
| `river_value_range=1` with a 0.3 prior | **-0.198** | -0.246 | | | -0.441 | reject |
| `draw_raise=0.5` | **-0.175** | -0.213 | | | -0.502 | reject |
| `commit_shove_eq=0.50` | -0.102 | -0.131 | | | -0.604 | reject |

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

| Candidate | Pool (seeds 101-104) | Field | range_pro | range_aggro | brown | vs `x_drew_fast` (seeds 1-8) | Verdict |
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
Pool here = range_pro, range_aggro, brown, adaptive, adaptive_loose,
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

| Candidate | Pool | Field | range_pro | range_aggro | brown | Worst field | Verdict |
|---|---|---|---|---|---|---|---|
| `post_pot_size_eq=0.70` | +0.018 (z 0.5) | +0.021 | -0.200 | -0.183 | +0.219 | mc_loose -0.673 | **reject** |

The screen's +0.12 to +0.17 against the three strongest bots did not
repeat on fresh seeds; it was most likely the unlucky base run batch 8
suspected. Not run against Drew's bot, since it already fails on the
closest pool bots.

### Batch 11: batch 8 finalists and river ideas (seeds 113-120, before `street_levels`)

27 opponents (the pool without `x_drew_real`, `agent` and six self
variants), 8 fresh seeds, plus an **A/A arm** with identical parameters.
The A/A arm came out -0.054 (z -7.4): against bots that read the real
clock the base itself moved by up to 0.6 bb/deal between two runs
(`brown` -0.62, `mc_basic` -0.57, `x_brown_real` -0.30). The paired
standard errors do not see this, so pool means against those bots are not
trustworthy under a loaded CPU. The A/A arm's diff was exactly 0 against
16 opponents (the baselines, `nit`, `maniac`, `weak_tight`,
`guide_example`, `checkfold`, `mc_loose`, `adaptive`, `barreler_half` and
the four self variants), so candidates are scored on those
("deterministic"), with the noisier strong bots alongside.

| Candidate | Deterministic 16 | Self variants | range_pro | range_aggro | x_brown_real | Verdict |
|---|---|---|---|---|---|---|
| A/A | 0.000 | 0.000 | +0.042 | -0.022 | -0.298 | noise floor |
| `river_bluff_adapt=1, river_bluff_min_obs=6` | **+0.062** (se 0.012) | **+0.195** | **+0.307** | **+0.232** | +0.190 | **keep** (re-checked on the new base, below) |
| `river_bluff_adapt=1` (12 observations) | +0.014 | +0.047 | +0.156 | +0.090 | +0.235 | weaker than 6 |
| `barrel_weight=0.4` | +0.136 | -0.054 | -0.216 | +0.178 | +0.123 | reject: gains on weak bots only |
| `barrel_weight=0.4, post_pot_size_eq=0.70` | +0.150 | -0.014 | +0.025 | +0.105 | +0.169 | reject: same pattern |
| `post_call_margin=-0.02` | +0.044 | -0.100 | -0.231 | +0.103 | +0.178 | reject |
| `post_bet_eq=0.63` | +0.021 | +0.006 | -0.144 | +0.161 | +0.185 | reject |
| `agg_bet=0.35` | +0.021 | -0.020 | -0.006 | +0.120 | +0.055 | reject |
| `river_bluff_freq=0.12` | -0.021 | -0.047 | -0.035 | +0.157 | +0.171 | reject |
| `post_pot_size_eq=0.70` | -0.010 | -0.084 | -0.029 | +0.167 | -0.300 | reject |
| `sb_raise_pot_above=0.75` | -0.051 | -0.051 | -0.072 | +0.193 | -0.434 | reject |
| `post_raise_eq=0.65` | -0.113 | -0.213 | -0.037 | +0.422 | -0.360 | reject |

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
arm. With 840 matches the CPU was less loaded and only `x_drew_fast`,
`x_brown_real` and `brown` moved in the A/A arm (+0.12, +0.07, +0.05).

| Candidate | Deterministic 18 | Self variants | range_pro | range_aggro | x_brown_real | x_drew_fast | Worst det |
|---|---|---|---|---|---|---|---|
| A/A | 0.000 | 0.000 | 0.000 | 0.000 | +0.073 | +0.118 (se 0.137) | 0.000 |
| `river_bluff_min_obs=6` | +0.055 (se 0.011) | +0.233 | +0.169 | +0.010 | +0.137 | +0.092 | -0.119 |
| **`river_bluff_min_obs=4`** | **+0.075** (se 0.013) | **+0.282** | **+0.214** | **+0.153** | +0.015 | +0.128 | -0.143 |
| `min_obs=6, margin=0.02` | +0.067 (se 0.012) | +0.232 | +0.307 | +0.015 | +0.159 | +0.084 | -0.035 |

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
0.40. 22 opponents, A/A arm; only `x_drew_fast` (+0.18) and `x_brown_real`
(-0.11) moved in the A/A arm.

| Candidate | Deterministic 20 | Self variants | range_aggro | x_brown_real | barreler | x_drew_fast | Worst det |
|---|---|---|---|---|---|---|---|
| A/A | 0.000 | 0.000 | 0.000 | -0.112 | 0.000 | +0.183 (se 0.112) | 0.000 |
| **`defend_gain=0.3`** | **+0.087** (se 0.029) | +0.052 | +0.114 | -0.073 | -0.098 | -0.131 (se 0.142) | always_half -0.146 |
| `defend_gain=0.5` | +0.052 | -0.022 | +0.190 | +0.029 | -0.148 | +0.008 | mc_loose -0.191 |
| `0.5, target 0.50` | +0.061 | +0.024 | +0.088 | -0.210 | -0.161 | -0.009 | barreler -0.161 |
| `0.5` with the river | +0.088 | +0.044 | +0.177 | -0.112 | -0.166 | -0.015 | barreler -0.166 |
| `0.8, cap 0.15` | +0.047 | +0.044 | +0.176 | -0.239 | -0.086 | +0.006 | mc_loose -0.414 |

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

## What to try next

Done since the last list: the preflop re-tune (batch 8, nothing beat the
current thresholds), `river_value_range` with a looser prior and
`draw_raise` (both clearly negative, batch 8), and the cheaper equity call
(kept, though extra samples turned out to be worth only about +0.05).

* **Drew's bot** is the closest opponent: at 1 CPU with its bank intact the
  Docker matches are mostly chops in our favour (+0.32 mean), and with 3x
  the thinking time (`x_drew_fast`) it beats ShortStack by 0.7-1.0 bb/deal. It bets most flops and
  sizes its bluffs to our measured fold rate; we fold 68% of flop bets and
  give up the best hand on a third of those folds. The minimum-defense
  option (`defend_gain`) is the first answer being tested; bet sizing and
  check-raising against its flop bets are the next.
* Judge A/B results on the opponents where the A/A arm is exactly 0, and
  run batches against real-clock bots (`x_drew_*`, `brown`) with fewer
  workers, or through Docker.
* Make `adaptive_loose` stop losing to `learn_postflop` (the one consistent
  negative).
