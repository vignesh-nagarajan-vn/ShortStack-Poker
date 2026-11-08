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

## Matches against other teams' Docker images

Build each bot with the organizers' Dockerfile (or `docker pull` an image a
team pushed), then play tournament-style: every half in fresh containers
with 1 CPU, 4 GB and read-only files, the judge on a private Docker network.
Run from Git Bash on Windows; results land in `results/container/`.

```bash
docker build -f docker/Dockerfile.agent -t shortstack:latest .
docker build -f docker/Dockerfile.agent -t rival:latest ../their-repo
./tools/container_match.sh shortstack:latest rival:latest 11 12 13
```

## Offline tools (`sim/`, not shipped in the image)

| Command | What it does |
|---|---|
| `python -m sim.run_match --a agent --b mc_basic --seeds 1 2` | In-process duplicate matches, scored like the judge |
| `python -m sim.league --focus agent --seeds 1 2 3` | Our bot vs the whole pool in parallel, as a standings table |
| `python -m sim.ab --cand "label:param=value" --seeds 101 102 103 104` | Paired A/B of parameter sets vs the baseline on the same seeds, with standard errors ([docs/experiments.md](docs/experiments.md)) |
| `python -m sim.ab --cand "aa:barrel_weight=0.6" ...` | An A/A arm (a default value): bots that read the real clock move between identical runs, so judge candidates on the opponents where the A/A diff is exactly 0. `vc_per_call=...,vc_per_sample=...` replays other equity costs on the virtual clock |
| `python -m sim.run_match --a agent --b x_drew_fast` | `x_brown_real` / `x_drew_real` load the real rival bots from `../heads-up-bot` and `../tamu-heads-up-bot`; `x_drew_fast` is Drew's bot on a 3x faster machine, so it keeps its time bank |
| `python -m sim.probe --opps brown barreler --seeds 1 2` | Per-opponent decision stats: fold-to-bet by street, folds that gave up the best hand, river bets called and won |
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
| `sim/` | Match runner, league, opponent pool, A/B harness, probe, tuner, benchmark. Our bot runs on a deterministic virtual clock in the simulator (`sim.players.VirtualClock`); real timing is checked through the judge |
