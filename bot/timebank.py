"""Keep our thinking time far inside the judge's 8 s per half.

The judge charges wall-clock time per request minus 1 ms, which includes
the web server's own JSON handling. We can only measure our own code, so
we budget a fraction of the bank for it, assume a fixed overhead per
request, and spread what is left over the decisions still to come.

The Monte Carlo sample count is derived from that allowance and a running
estimate of the cost per sample, with a hard cap per decision. When the
bank gets low, samples() returns 0 and the strategy falls back to
table-only decisions that cost microseconds.
"""

from __future__ import annotations

import time

# Measured with the real judge on a dev laptop: ~0.29 ms charged per request
# beyond our own code (FastAPI + JSON, after the 1 ms grace). Padded 2x for
# a slower tournament machine.
OVERHEAD_PER_REQUEST = 0.0006   # seconds charged per request beyond our code
SHARE_FOR_LOGIC = 0.45          # fraction of the bank our own code may spend
FALLBACK_HEADROOM = 2.5         # cheap 40-sample estimates only while this much bank is left
HARD_CAP_SECONDS = 0.030        # never think longer than this on one decision
MIN_SAMPLES = 60                # below this, equity is too noisy to be worth the time
MAX_SAMPLES = 1500


class TimeBank:
    def __init__(self, bank_seconds: float = 8.0, num_hands: int = 1000,
                 share: float = SHARE_FOR_LOGIC, max_samples: int = MAX_SAMPLES,
                 clock=time.perf_counter) -> None:
        self.clock = clock            # the simulator swaps in a deterministic clock
        self.share = share
        self.max_samples = int(max_samples)
        self.bank = bank_seconds
        self.num_hands = max(1, num_hands)
        self.spent = 0.0              # our own measured time
        self.requests = 0
        self.decisions = 0
        self.cost_per_sample = 4e-6   # refined from measurements
        self._t0 = 0.0

    # --- measuring ---------------------------------------------------------

    def begin(self) -> None:
        self._t0 = self.clock()

    def end(self, is_request: bool = True) -> float:
        elapsed = self.clock() - self._t0
        self.spent += elapsed
        if is_request:
            self.requests += 1
        return elapsed

    def record_samples(self, n: int, elapsed: float) -> None:
        """Update the per-sample cost estimate from a real equity call."""
        if n > 0 and elapsed > 0:
            self.cost_per_sample = 0.8 * self.cost_per_sample + 0.2 * (elapsed / n)

    # --- budgeting ---------------------------------------------------------

    def charged_estimate(self) -> float:
        """Our best guess of what the judge has charged so far."""
        return self.spent + self.requests * OVERHEAD_PER_REQUEST

    def remaining_logic(self) -> float:
        return self.bank * self.share - self.spent

    def allowance(self, hand_index: int) -> float:
        """Seconds we may spend on this decision."""
        hands_left = max(1, self.num_hands - hand_index)
        per_hand = max(2.0, self.decisions / max(1, hand_index)) if hand_index else 3.0
        remaining = min(self.remaining_logic(),
                        self.bank - 0.5 - self.charged_estimate() - hands_left * per_hand * OVERHEAD_PER_REQUEST)
        if remaining <= 0:
            return 0.0
        return min(HARD_CAP_SECONDS, remaining / (hands_left * per_hand))

    def samples(self, hand_index: int) -> int:
        """Monte Carlo samples affordable now (0 = use table-only play)."""
        n = int(self.allowance(hand_index) / max(self.cost_per_sample, 1e-7))
        if n < MIN_SAMPLES:
            return 0
        return min(self.max_samples, n)
