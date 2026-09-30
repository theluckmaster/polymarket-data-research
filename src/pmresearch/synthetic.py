"""Seeded synthetic trade streams for tests and demos.

The repo ships no real market data. A driftless random walk is the null
hypothesis every signal should fail to beat. A trending walk is a positive
control that shows the harness *can* detect an edge when one exists.
"""

from __future__ import annotations

import numpy as np

from pmresearch.models import Trade


def random_walk_trades(
    duration_s: float,
    *,
    seed: int = 0,
    start_ts: float = 1_700_000_100.0,
    start_price: float = 60_000.0,
    trades_per_s: float = 2.0,
    vol_per_sqrt_s: float = 2e-4,
    drift_per_s: float = 0.0,
    drift_block_s: float | None = None,
    symbol: str = "SYNTHUSD",
) -> list[Trade]:
    """Poisson trade arrivals over a geometric random walk.

    With ``drift_block_s`` set, the drift keeps its magnitude but flips to a
    random sign every block, producing trends that persist across several
    windows: the kind of structure a momentum signal needs to have an edge.
    """
    rng = np.random.default_rng(seed)
    n = rng.poisson(trades_per_s * duration_s)
    ts = np.sort(rng.uniform(0.0, duration_s, n)) + start_ts
    dt = np.diff(ts, prepend=start_ts)
    drift = np.full(n, drift_per_s)
    if drift_block_s:
        n_blocks = int(duration_s // drift_block_s) + 1
        signs = rng.choice([-1.0, 1.0], n_blocks)
        drift *= signs[((ts - start_ts) // drift_block_s).astype(int)]
    returns = rng.standard_normal(n) * vol_per_sqrt_s * np.sqrt(dt) + drift * dt
    prices = start_price * np.exp(np.cumsum(returns))
    qty = rng.exponential(0.05, n)
    sides = np.where(rng.random(n) < 0.5, "buy", "sell")
    return [
        Trade(float(t), float(round(p, 2)), float(q), symbol, str(s))
        for t, p, q, s in zip(ts, prices, qty, sides)
    ]
