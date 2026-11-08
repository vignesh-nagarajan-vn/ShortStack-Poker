# Mega prompt: make ShortStack as strong as possible

Paste everything below the line into a fresh Claude Code chat opened in this repo.

---

You are improving **ShortStack**, our bot for the TAMU Datathon Poker Bot Challenge. It's in this repository. Your goal is to raise its expected score against the real tournament field as much as you can, measured with honest experiments, without risking a forfeit. Work in a loop: measure, change one thing, measure again, keep it only if the numbers say so. Plan for a long session. Make many small, verified improvements, not one big rewrite.

## The game and the hard rules

- Heads-up Short Deck (36 cards, 6 to A) 5-card Pot-Limit Omaha. A hand is exactly 2 hole cards plus 3 board cards. A flush beats a full house, and three of a kind beats a straight.
- Actions: `FOLD`, `CHECK_CALL`, `RAISE_HALF`, `RAISE_POT`. At most 4 raises per street. Stacks are 80 chips (40 bb) at the start of every hand.
- A match is 1,000 duplicate deals: two halves of 1,000 hands with seats swapped and the same cards. The score is chips won, and a match is won when the confidence interval clears zero. A bot that forfeits either half loses the match.
- **The time bank is 8 s of thinking per half.** When it runs out, the judge plays check-or-fold for that bot for the rest of the half. In the tournament every half runs in a **brand-new server process**, so nothing carries over between halves. The tournament machine may be slower than this laptop.
- The tournament runs `agent.py` from the repo root, built with `docker/Dockerfile.*`. Image size is limited, and `.dockerignore` keeps `sim/`, `tests/` and `tools/` out of it. Never break `agent.py`'s server plumbing, `requirements.txt`, or the safety wrapper in `bot/safety.py`.
- Every action must be legal. Exceptions must fall back to a legal action and never become errors (10 errors forfeits).

## Read first

1. `README.md` and `EXTENDED.md`: what the bot does, the commands, and the code map.
2. `bot/params.py`: every tunable number. `bot/strategy.py`: all decisions. `bot/core.py`: per-half state (`Brain`).
3. `bot/opponent.py`, `bot/profile.py`, `bot/showdown.py`, `bot/image.py`, `bot/autopilot.py`: opponent modelling and exploitation.
4. `bot/equity.py`, `bot/fasteval.py`, `bot/ranges.py`, `bot/timebank.py`: fast vectorised Monte Carlo against a weighted opponent range, plus the time budget.
5. `sim/`: in-process match runner (`sim.run_match`), the opponent pool (`sim/pool.py`, `sim/opponents.py`), the league (`sim.league`), the coordinate-search tuner (`sim.tune`) and the benchmark (`sim.bench`).
6. Run `git status` and `git log --oneline -10`. The working tree may hold an uncommitted "thin river value" change (`thin_river_*` params, `OpponentModel.river_called_wins`, `Strategy.thin_river_shift`). Treat it as part of the baseline. It measured +0.41 bb/deal across the pool. If it isn't committed yet, ask me before committing it.

## What we already know (measured, November 2026)

Against **BrownBallers** (a rival bot, https://github.com/snr2753423/heads-up-bot), run through the real HTTP judge with fresh servers each half, ShortStack won 10 of 10 matches at about +1.1 to +2.4 bb/deal. Hand-log analysis:

- **Working:** showdown value (+8,089 bb, 56% won). River value bets that get called are ahead about 85% of the time. River folds are 98% correct, and flop and turn folds 84 to 88% correct. Autopilot detection (raising every hand once the opponent's bank is empty) added about +0.75 bb/hand in the second part of each half. It uses about 3.3 to 4.1 s of the 8 s bank with 0 errors.
- **Weak spots or room to gain:**
  - River value is still too tight against loose callers. Even after the thin-river change, called river bets win 86%, so the shift (max 0.10) can probably go further, or use a different signal.
  - River bluffing is almost nonexistent (about 1 to 2% of river bets that get folds). `river_bluff_freq` is 0.06, in position only.
  - It folds 53% of the time facing postflop bets, against the rival's 27%. It folded the eventual winner 183 times on flop and turn, in pots of about 1,670 bb. That's mostly correct against an honest bettor, but against bluffier bots this could be a leak.
  - Preflop it calls 77% of raises and 3-bets about 9%. Neither has been examined closely.
  - It spends only about 3.8 s of an 8 s bank (the logic cap is 45%). That headroom could buy more Monte Carlo samples in big pots, but keep a safety margin for a slower machine.
- **What rival bots get wrong:** BrownBallers computes equity against a *random* hand, so it calls the river with weak hands (only 7 to 10% of its river calls were ahead). It uses the slow `omaha_score` with 32 to 48 samples, so its estimates are noisy and it runs out of time 100 to 500 decisions before the half ends. Many field bots will look like this. That's the "MC equity vs one random hand" family that `sim/pool.py` already models.

## How to measure (non-negotiable)

1. **Paired A/B with the same seeds.** Build `sim/ab.py` (if it doesn't exist) that plays the candidate (`BrainPlayer` with overrides) and the current baseline against **every bot in `sim.pool.registry()`** on the same seeds, 1,000 deals each, in a `ProcessPoolExecutor`. It should print per-opponent bb/deal for both arms, the difference, the pool mean difference, and a standard error from the per-seed differences. Use at least 4 seeds while exploring and at least 8 before keeping a change.
2. **Keep rule:** keep a change only if the pool mean difference is at least +0.05 bb/deal, it is more than about 2 standard errors from zero, and no non-self opponent drops by more than 0.3 bb/deal. Self-play variants (`self_*`) are mostly noise, but watch for a consistent pattern.
3. **Real-judge check** for anything that touches timing or the HTTP path: run `agent.py` against baselines and a rival bot through `judge_engine.py`, tournament-style (`--half 1`, restart both servers, `--half 2`, then `combine`). Clone https://github.com/snr2753423/heads-up-bot into a separate directory outside the repo and run it on another port (`PORT=5010 python agent.py`). Look at the time-bank line: ShortStack must stay under about 5 s of 8 s.
4. **Slow-machine check:** simulate a machine 2x slower (for example, double every timing the `TimeBank` measures, or add a sleep in a test harness) and confirm the bank still never empties.
5. Run `python -m pytest -q` after every kept change and `./tools/check_build.sh` (Docker, Git Bash) before finishing.
6. **Don't overfit the pool.** The pool is our guess at the field. Prefer changes that adapt to what the opponent actually does over fixed constant changes that only beat our own opponents. When you add an exploit, add the opponent it targets to the pool, and check it doesn't hurt bots it's not aimed at.

Keep a running log in `EXTENDED.md` (or a new `docs/experiments.md`) with what you tried, the numbers, and whether you kept it. Rejected ideas are worth recording too.

## Improvement backlog (rough priority; your judgement wins)

1. **Better opponents in the pool first.** Add an in-process clone of BrownBallers' logic (equity against a random hand with few samples, the thresholds from its `strategy/policy.py`, and its 8 s drain), plus at least one *strong* range-aware opponent (for example, ShortStack with different seeds and params). Without tough opponents, tuning only learns to beat weak bots.
2. **River value sizing and thinness.** Test `thin_river_shift` at 0.15 and 0.20. Also try applying the shift to river raises (not only bets when checked to). Learn the opponent's river calling range from showdowns (strength percentile of hands that called our river bets) and bet whenever our equity against *that* range clears the threshold. Choose pot versus half pot based on how the opponent's call rate changes with size.
3. **River bluffs that adapt.** Track the opponent's river fold-to-bet separately for half-pot and pot bets. A half-pot bluff needs more than 33% folds and a pot bluff needs more than 50%. Bluff our worst hands (blockers count in PLO5, though less than in Hold'em) when the measured fold rate clears the break-even with margin. Turn it off automatically against stations. Check that `bot/image.py` limits still hold.
4. **Postflop defence against aggressive bots.** Measure our fold-to-bet against each pool opponent and where it costs us. Consider check-raises with strong draws, and calling or raising more with nut-flush draws, wraps and sets when the opponent's bet frequency is high. `learn_postflop` was turned off after an ablation, so re-test it now that the pool is stronger.
5. **Preflop.** Re-tune the SB open, BB defence and 3-bet thresholds with the stronger pool. In PLO5 with 40 bb stacks, pot-control and SPR effects matter. Check `commit_ratio` and `low_spr` behaviour.
6. **Spend the spare time bank on the decisions that matter.** Give more samples to big-pot flop and turn decisions and fewer to trivial ones. Measure the actual EV gain from 2x samples before paying for it, and keep the slow-machine margin.
7. **Make slow opponents pay.** Opponents that drain their bank pay per decision. Lines that create more opponent decisions (and flop decisions, which are the most expensive for MC bots) drain them sooner, and our autopilot steal then wins every remaining hand. Test whether a small EV-neutral shift (for example, limping or calling more where it's close) makes opponents like `mc_drain`/`mc_greedy`/BrownBallers time out earlier, while staying even against fast bots. Only keep it if the full-pool numbers agree.
8. **Earlier autopilot detection.** It triggers after 10 default actions in a row (4 of them folds). Check whether a lower threshold catches timeouts sooner without misfiring on genuine check/fold nits. A misfire costs us chips.
9. **Robustness.** Fuzz the HTTP path with odd observations, re-run the timing tests, and make sure the Docker build passes and the image size is fine.

## How to work

- One hypothesis at a time. Write it down, implement it behind a param in `bot/params.py` with the current behaviour as the "off" value, A/B it, then keep or revert.
- Small, readable commits, one per kept improvement. Ask me before committing, pushing, or deleting anything. Don't touch the organizer files (`game.py`, `judge_engine.py`, `evaluator.py`, `docker/`).
- After each batch of kept changes, run the full league (`python -m sim.league --focus agent --seeds 1 2 3`) and the real-judge check, then update the README numbers so every claim matches a run you did.
- At the end, give me a table of what you tried, the bb/deal change for each, what you kept, and what you'd try next.
