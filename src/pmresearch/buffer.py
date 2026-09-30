"""Bounded ring buffer of trades with rolling analytics."""

from __future__ import annotations

import math
from collections import deque

import numpy as np

from pmresearch.models import Trade


class TickBuffer:
    """Keeps the most recent *max_size* trades; oldest are evicted first.

    Time-windowed methods walk backwards from the newest tick and stop at the
    window edge, so their cost scales with the window, not the buffer.
    """

    __slots__ = ("_buf", "_max_size")

    def __init__(self, max_size: int = 5000) -> None:
        if max_size < 1:
            raise ValueError("max_size must be >= 1")
        self._max_size = max_size
        self._buf: deque[Trade] = deque(maxlen=max_size)

    def add(self, trade: Trade) -> None:
        if self._buf and trade.ts < self._buf[-1].ts:
            raise ValueError("trades must be added in timestamp order")
        self._buf.append(trade)

    @property
    def size(self) -> int:
        return len(self._buf)

    @property
    def last(self) -> Trade | None:
        return self._buf[-1] if self._buf else None

    def last_n(self, n: int) -> list[Trade]:
        if n <= 0:
            return []
        n = min(n, len(self._buf))
        return [self._buf[i] for i in range(len(self._buf) - n, len(self._buf))]

    def vwap(self, window_s: float) -> float | None:
        if not self._buf:
            return None
        cutoff = self._buf[-1].ts - window_s
        pv = v = 0.0
        for t in reversed(self._buf):
            if t.ts < cutoff:
                break
            pv += t.price * t.qty
            v += t.qty
        return pv / v if v > 0 else None

    def price_at_or_before(self, ts: float) -> float | None:
        """Last traded price at or before *ts* (no look-ahead)."""
        for t in reversed(self._buf):
            if t.ts <= ts:
                return t.price
        return None

    def rate_of_change(self, window_s: float) -> float | None:
        """Fractional price change over the last *window_s* seconds."""
        if len(self._buf) < 2:
            return None
        now = self._buf[-1]
        past = self.price_at_or_before(now.ts - window_s)
        if past is None or past == 0:
            return None
        return (now.price - past) / past

    def ema(self, period: int) -> float | None:
        ticks = self.last_n(period)
        if not ticks:
            return None
        alpha = 2.0 / (period + 1)
        value = ticks[0].price
        for t in ticks[1:]:
            value = alpha * t.price + (1 - alpha) * value
        return value

    def volatility(self, n: int) -> float | None:
        """Sample std-dev of per-tick log returns over the last *n* ticks.

        Not annualised: tick spacing is irregular, so any annualisation
        factor would be misleading.
        """
        prices = self.prices(n)
        if len(prices) < 3 or np.any(prices <= 0):
            return None
        vol = float(np.std(np.diff(np.log(prices)), ddof=1))
        return vol if math.isfinite(vol) else None

    def prices(self, n: int | None = None) -> np.ndarray:
        ticks = list(self._buf) if n is None else self.last_n(n)
        return np.fromiter((t.price for t in ticks), dtype=np.float64, count=len(ticks))

    def timestamps(self, n: int | None = None) -> np.ndarray:
        ticks = list(self._buf) if n is None else self.last_n(n)
        return np.fromiter((t.ts for t in ticks), dtype=np.float64, count=len(ticks))
