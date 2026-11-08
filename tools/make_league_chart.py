"""Rebuild docs/images/league.png from a sim.league standings table.

    python -m sim.league --focus agent --seeds 1 2 3 --workers 6 > results/league.txt
    python tools/make_league_chart.py results/league.txt

Plots ShortStack's margin against every non-self bot in the table (the
"field"), sorted, with the win/chop/loss count in the title.
"""

from __future__ import annotations

import os
import re
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "images", "league.png")
LABELS = {"guide_example": "guide example bot"}
BAR, TEXT, MUTED, GRID, BG = "#2b7bd9", "#111111", "#555555", "#e6e6e6", "#fbfbfa"


def field_rows(path: str) -> list[tuple[str, float, tuple[int, int, int]]]:
    """(bot, bb/deal for the bot, W-C-L) for every non-self bot in the table."""
    rows = re.findall(r"^(\S+)\s+[\d.]+\s+(\d+)-(\d+)-(\d+)\s+([+-][\d.]+)", open(path).read(), re.M)
    return [(name, float(bb), (int(w), int(c), int(l))) for name, w, c, l, bb in rows
            if name != "agent" and not name.startswith("self_")]


def main(path: str) -> None:
    rows = field_rows(path)
    # A bot's losses are our wins and the other way round.
    wins = sum(wcl[2] for _, _, wcl in rows)
    chops = sum(wcl[1] for _, _, wcl in rows)
    losses = sum(wcl[0] for _, _, wcl in rows)
    data = sorted(((LABELS.get(n, n.replace("_", " ")), -bb) for n, bb, _ in rows), key=lambda x: x[1])

    fig, ax = plt.subplots(figsize=(13.5, 9.3), dpi=100)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    names, margins = zip(*data)
    ax.barh(names, margins, color=BAR, height=0.5, zorder=2)
    for y, m in enumerate(margins):
        ax.text(m + 0.13, y, f"{m:+.2f}", va="center", fontsize=11.5, color=TEXT)
    ax.set_title(f"{wins} wins, {chops} chops, {losses} losses against the {len(rows)}-bot field",
                 loc="left", fontsize=17, fontweight="bold", color=TEXT, pad=14)
    ax.set_xlabel("ShortStack's margin, bb/deal (3 duplicate matches of 1,000 deals each)",
                  fontsize=13, color=MUTED, labelpad=10)
    ax.set_xlim(0, max(margins) * 1.13)
    ax.grid(axis="x", color=GRID, zorder=0)
    ax.tick_params(axis="y", length=0, labelsize=12.5, labelcolor=MUTED)
    ax.tick_params(axis="x", labelsize=12.5, labelcolor=MUTED, color=GRID)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#bbbbbb")
    fig.tight_layout()
    fig.savefig(OUT, facecolor=BG)
    print(f"wrote {OUT}: {wins}-{chops}-{losses} vs {len(rows)} bots, "
          f"{min(margins):+.2f} to {max(margins):+.2f} bb/deal")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "results", "league_final4.txt"))
