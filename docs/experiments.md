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

## What to try next

* Preflop re-tune (`sb_raise_half_above`, `bb_raise_above`,
  `pre_reraise_equity`, `pre_call_margin_oop`, `commit_ratio`) against the
  new pool, now that A/B noise is low enough to see 0.05 bb/deal.
* `river_value_range` with a looser calling-floor prior (0.3 instead of 0.5)
  and fewer showdowns needed, so stations stop being under-bet.
* Draw semi-bluff raises vs frequent bettors (`draw_raise`, wired up but
  not yet tested).
* More samples on big pots (`logic_share`, `mc_max_samples`), measured with
  the virtual clock first, then checked on the real judge with the slow-machine
  margin.
* Make `adaptive_loose` stop losing to `learn_postflop` (the one consistent
  negative).
