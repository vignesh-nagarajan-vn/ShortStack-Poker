# ShortStack

**Heads-up Short Deck 5-card Pot-Limit Omaha bot for the TAMU Datathon Poker Bot Challenge.**

- Starter bundle: [tamu-datathon-org/heads-up-bundle](https://github.com/tamu-datathon-org/heads-up-bundle)
- Participant guide: [docs/starter-guide.md](docs/starter-guide.md)

ShortStack plays 1,000-deal duplicate matches against every other team's bot. It scores hands with a vectorized numpy evaluator, takes Monte Carlo equity against the opponent's *range* (weighted by their betting line) instead of a random hand, and adapts to each opponent within the half: it learns their ranges from showdowns, shifts its play against maniacs, nits and calling stations, and steals every hand from bots whose time bank has run out.

- **Team:** Vignesh Nagarajan, Srivanth Rudrangi, Aaron Jacob, Anish Koduri
- **Stack:** Python, numpy, FastAPI (organizer plumbing, unchanged)
- **Run it:** `pip install -r requirements-dev.txt`, then `python -m pytest -q`; see [EXTENDED.md](EXTENDED.md) for matches, the league and the build check

## How it works

Most of the field will compute equity with `omaha_score`, which costs about **75 µs** per call, so naive simulation drains the **8 s** time bank and the judge then plays check-or-fold for them. ShortStack precomputes a **630 x 7140** rank table, which scores an Omaha hand in about **1.3 µs** in batches (about **3 µs** per Monte Carlo sample). Preflop decisions read a table of equity vs a random hand for all **376,992** starting hands. Postflop, sampled opponent hands are weighted by their preflop percentile and by how strong their made hand must be to explain their bets, so a pot-sized bet isn't treated like a random hand. Calls are priced between the pot odds and the all-in odds, depending on how often the opponent keeps betting. After **10** default actions in a row (including **4** folds), it raises every hand. Its own logic spends at most **45%** of the time bank, and every answer is checked for legality, so it can't forfeit on errors.

Against an opponent pool built to look like the expected field (organizer baselines, the guide's example bot, MC-equity threshold bots, adaptive exploiters and self-play variants), the tuned bot went **36-0-0** against 12 of those bots on three fresh seeds, at **+3.92 bb/deal**. Through the real HTTP judge it beat the random baseline by **+6.19 bb/deal** and the always-pot baseline by **+5.93**. Played tournament-style (each half on freshly started servers), it beat the always-half baseline by **+5.43** (95% CI +3.91 to +6.96). Every match used about **4.1-4.3 s** of the 8 s bank, with **0 errors**.

The pool is our model of other teams, not the real field, so margins against actual submissions will differ. Timing was measured on a laptop; the tournament machine may be slower, which the time bank absorbs by sampling less.
