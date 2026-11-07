# ShortStack: extended notes

## Setup and tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

## Real matches through the judge

Run each in its own terminal. On Windows, use `127.0.0.1`: `localhost` may resolve to IPv6, which uvicorn doesn't listen on.

```bash
python agent.py
python baseline-bots/baseline_random.py
python judge_engine.py --agent1 http://127.0.0.1:5008 --agent2 http://127.0.0.1:5009
```

## Tournament build check

Needs Docker; on Windows, run it from Git Bash.

```bash
./tools/check_build.sh
```

## Offline tools (`sim/`, not shipped in the image)

| Command | What it does |
|---|---|
| `python -m sim.run_match --a agent --b mc_basic --seeds 1 2` | In-process duplicate matches, scored like the judge |
| `python -m sim.league --focus agent --seeds 1 2 3` | Our bot vs the whole pool in parallel, as a standings table |
| `python -m sim.tune --rounds 1` | Coordinate search over `bot/params.py` against the pool |
| `python -m sim.bench` | Evaluator and equity timings |
| `python tools/build_tables.py`, `python tools/build_preflop_table.py` | Rebuild the shipped data files |

## Code map

| File | Role |
|---|---|
| `agent.py` | Organizer server plumbing; the three hooks delegate to `bot/` behind a safety wrapper |
| `bot/fasteval.py`, `bot/equity.py` | Numpy rank table and vectorized Monte Carlo equity |
| `bot/preflop.py` | Preflop equity and percentile lookups from `data/preflop_equity.npz` |
| `bot/strategy.py`, `bot/params.py` | Decisions and every tunable threshold |
| `bot/ranges.py`, `bot/draws.py` | Range weights for sampled opponent hands; draws under the 2 + 3 rule |
| `bot/opponent.py`, `bot/showdown.py` | Opponent statistics and ranges learned from showdowns |
| `bot/profile.py`, `bot/autopilot.py`, `bot/image.py` | Profile exploits, autopilot stealing, self-image control |
| `bot/timebank.py` | Time budgeting and adaptive sample counts |
| `sim/` | Match runner, league, opponent pool, tuner, benchmark |
