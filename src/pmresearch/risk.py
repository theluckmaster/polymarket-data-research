"""Position-sizing and session risk controls (research concepts).

The clock is injectable so the same controls run against replay time in a
backtest and wall time elsewhere.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime


def kelly_binary(p_win: float, price: float) -> float:
    """Kelly fraction for buying a binary contract at *price* that pays 1.

    Net odds are ``b = (1 - price) / price``, so ``f* = (p - price) / (1 - price)``.
    Returns 0 when there is no positive edge or inputs are out of range.
    """
    if not (0.0 < price < 1.0) or not (0.0 <= p_win <= 1.0):
        return 0.0
    return max((p_win - price) / (1.0 - price), 0.0)


def fractional_kelly(p_win: float, price: float, fraction: float = 0.5, cap: float = 0.05) -> float:
    """Scaled-down Kelly with a hard per-trade cap.

    Full Kelly assumes *p_win* is known exactly; estimates never are, so
    research sizing uses a fraction of it and a ceiling.
    """
    return min(kelly_binary(p_win, price) * fraction, cap)


@dataclass(frozen=True, slots=True)
class RiskCheck:
    allowed: bool
    reason: str = ""


class RiskManager:
    """Daily loss cap plus a cooldown after consecutive losses."""

    def __init__(
        self,
        starting_bankroll: float,
        *,
        daily_loss_cap_pct: float = 0.10,
        cooldown_after_losses: int = 3,
        cooldown_s: float = 900.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if starting_bankroll <= 0:
            raise ValueError("starting_bankroll must be positive")
        self._loss_cap = starting_bankroll * daily_loss_cap_pct
        self._cooldown_after = cooldown_after_losses
        self._cooldown_s = cooldown_s
        self._clock = clock
        self._day = self._utc_day()
        self.daily_pnl = 0.0
        self.consecutive_losses = 0
        self._cooldown_until = 0.0

    def _utc_day(self) -> str:
        return datetime.fromtimestamp(self._clock(), tz=UTC).strftime("%Y-%m-%d")

    def _roll_day(self) -> None:
        today = self._utc_day()
        if today != self._day:
            self._day = today
            self.daily_pnl = 0.0
            self.consecutive_losses = 0
            self._cooldown_until = 0.0

    def check(self) -> RiskCheck:
        self._roll_day()
        now = self._clock()
        if now < self._cooldown_until:
            return RiskCheck(False, f"cooldown ({self._cooldown_until - now:.0f}s left)")
        if self.daily_pnl <= -self._loss_cap:
            return RiskCheck(False, "daily loss cap reached")
        return RiskCheck(True)

    def record(self, pnl: float) -> None:
        self._roll_day()
        self.daily_pnl += pnl
        if pnl < 0:
            self.consecutive_losses += 1
            if self.consecutive_losses >= self._cooldown_after:
                self._cooldown_until = self._clock() + self._cooldown_s
                self.consecutive_losses = 0
        else:
            self.consecutive_losses = 0
