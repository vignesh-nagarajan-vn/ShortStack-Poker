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

## What to try next

* Preflop re-tune (`sb_raise_half_above`, `bb_raise_above`,
  `pre_reraise_equity`, `pre_call_margin_oop`, `commit_ratio`) against the
  new pool, now that A/B noise is low enough to see 0.05 bb/deal.
* `river_value_range` with a looser calling-floor prior (0.3 instead of 0.5)
  and fewer showdowns needed, so stations stop being under-bet.
* Draw semi-bluff raises vs frequent bettors (`draw_raise`, wired up but
  not yet tested).
* Cut the fixed 0.35 ms cost of each equity call (vectorize the preflop
  percentile and made-strength weights), which turns straight into samples;
  batch 6 shows samples are worth about 0.25 bb/deal per 0.1 of `logic_share`.
* Make `adaptive_loose` stop losing to `learn_postflop` (the one consistent
  negative).
