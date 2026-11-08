# Short prompt: improve BrownBallers (friend's bot)

Paste everything below the line into a fresh Claude Code chat opened in the friend's repo (https://github.com/snr2753423/heads-up-bot).

---

You're improving this bot for the TAMU Datathon Poker Bot Challenge: heads-up Short Deck 5-card PLO, 1,000 duplicate deals per match, an 8 s thinking budget per half, and a fresh server each half. The strategy lives in `strategy/` and is called from `agent.py`. Keep `agent.py`'s server plumbing, `requirements.txt` and the organizer files (`game.py`, `judge_engine.py`, `evaluator.py`, `docker/`) as they are.

A tournament-style test (10 halves against a strong opponent, real judge) found these problems, from most to least costly:

1. **It runs out of time every half.** The 8 s bank empties between deal 490 and 870, and the judge then plays check-or-fold for 100 to 500 decisions. A good opponent steals every one of those hands. Causes: `evaluator.omaha_score` is slow (about 75 µs a call), postflop Monte Carlo costs about 3 to 24 ms per decision, and the first preflop lookup builds a 377k-entry dict (about 0.5 s) *inside* the first request. Fix: build tables at import or startup, not in a request. Precompute a rank lookup and vectorise scoring with numpy. Add a time-budget tracker that cuts samples as the bank shrinks, so the bank never empties.
2. **Equity against a random hand.** It ignores what the opponent's bets say. Only 7 to 10% of its river calls were ahead. Weight sampled opponent hands by their betting line (a bet or raise means a stronger range, more so on later streets and after several bets), and learn those ranges from showdowns.
3. **Noisy estimates.** 32 to 48 samples give about ±7% equity error, which is wider than the gaps between its thresholds. Once scoring is fast, use hundreds to thousands of samples.
4. **Thin river value.** Its river bets that got called were ahead only about 50% of the time. Bet the river for value only with hands that beat the opponent's *calling* range.
5. **Folding too much from the small blind.** It folds 20% preflop, where 5% or less is typical for good bots at these stacks.

How to work:
- Test with `judge_engine.py` against the baselines in `baseline-bots/`, tournament-style: run `--half 1`, restart both bots, run `--half 2`, then `combine`. Use several seeds. Check the time-bank line every run: target under 5 s of 8 s.
- Change one thing at a time, compare on the same seeds, and keep it only if it improves results without new errors or timeouts.
- Run `python -m pytest -q` and `./tools/check_build.sh` before finishing. Ask before committing or pushing.
- Finish with a short table: each change, before and after bb/deal, and the time-bank use.
