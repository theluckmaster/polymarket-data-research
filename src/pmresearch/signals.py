"""Research features computed from a :class:`TickBuffer`.

These are hypotheses to test, not validated predictors. The backtester and
its tests exist to check them against a no-skill baseline.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

import numpy as np

from pmresearch.buffer import TickBuffer

Direction = Literal["UP", "DOWN", "NEUTRAL"]


@dataclass(frozen=True, slots=True)
class MomentumSignal:
    direction: Direction
    strength: float  # 0..1
    ema_spread: float  # (fast - slow) / slow
    roc: float  # blended rate of change


def momentum(
    buf: TickBuffer,
    *,
    fast: int = 10,
    slow: int = 50,
    roc_windows_s: tuple[float, ...] = (10.0, 30.0, 60.0),
    neutral_band: float = 0.05,
    scale: float = 1000.0,
) -> MomentumSignal:
    """EMA crossover blended with multi-window rate of change.

    Each component is scaled and clipped to [-1, 1] (``scale=1000`` maps a
    0.1% move to full strength), then averaged. Scores inside
    ±*neutral_band* are NEUTRAL.
    """
    if buf.size < slow:
        return MomentumSignal("NEUTRAL", 0.0, 0.0, 0.0)
    f, s = buf.ema(fast), buf.ema(slow)
    ema_spread = (f - s) / s if f is not None and s else 0.0
    rocs = [r for w in roc_windows_s if (r := buf.rate_of_change(w)) is not None]
    roc = float(np.mean(rocs)) if rocs else 0.0

    score = 0.5 * np.clip(ema_spread * scale, -1, 1) + 0.5 * np.clip(roc * scale, -1, 1)
    direction: Direction = "UP" if score > neutral_band else "DOWN" if score < -neutral_band else "NEUTRAL"
    return MomentumSignal(direction, float(min(abs(score), 1.0)), ema_spread, roc)


class Regime(Enum):
    TRENDING = "trending"
    RANGING = "ranging"
    CHOPPY = "choppy"
    QUIET = "quiet"


def directional_efficiency(prices: np.ndarray) -> float:
    """|net move| / path length, in [0, 1]. 1 = straight line, ~0 = noise."""
    if len(prices) < 2:
        return 0.0
    path = float(np.sum(np.abs(np.diff(prices))))
    return 0.0 if path == 0 else float(abs(prices[-1] - prices[0]) / path)


def classify_regime(
    buf: TickBuffer,
    *,
    window: int = 50,
    quiet_vol: float = 1e-5,
    trend_efficiency: float = 0.4,
    chop_efficiency: float = 0.1,
) -> Regime:
    """Coarse regime label used to gate or segment signals in research."""
    prices = buf.prices(window)
    if len(prices) < window:
        return Regime.QUIET
    vol = buf.volatility(window)
    if vol is None or vol < quiet_vol:
        return Regime.QUIET
    eff = directional_efficiency(prices)
    if eff >= trend_efficiency:
        return Regime.TRENDING
    if eff <= chop_efficiency:
        return Regime.CHOPPY
    return Regime.RANGING
