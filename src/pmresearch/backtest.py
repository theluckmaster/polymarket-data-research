"""Event-driven replay of fixed-length UP/DOWN windows.

Model: time is cut into windows of ``window_s`` seconds aligned to the epoch
(like 5-minute "will the price be higher at the end?" markets). At
``window_start + decide_after_s`` the strategy sees a buffer containing only
trades with ``ts <= decision time`` and may take one side at an assumed
contract price. The window resolves UP if the last price at or before the
window end is >= the reference price at the window start.

Look-ahead is prevented structurally: trades are fed to the buffer in time
order and the strategy is called before any later trade is added. Direction
and outcome therefore come from disjoint data.

Simplifications (stated so results are not over-read): the contract price is
a fixed parameter rather than a recorded order book, fills are assumed at
that price, and fees are a flat fraction of stake.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Literal

from pmresearch.buffer import TickBuffer
from pmresearch.metrics import Summary, summarize
from pmresearch.models import Trade
from pmresearch.risk import RiskManager

Side = Literal["UP", "DOWN"]
Strategy = Callable[[TickBuffer, float], Side | None]


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    window_s: float = 300.0
    decide_after_s: float = 0.0
    entry_price: float = 0.50
    fee_rate: float = 0.02  # fraction of stake
    stake: float = 1.0
    use_risk_manager: bool = True
    starting_bankroll: float = 100.0


@dataclass(frozen=True, slots=True)
class TradeRecord:
    window_start: float
    side: Side
    reference_price: float
    settle_price: float
    won: bool
    pnl: float


@dataclass
class BacktestResult:
    config: BacktestConfig
    trades: list[TradeRecord] = field(default_factory=list)
    windows_seen: int = 0
    skipped_by_risk: int = 0

    @property
    def summary(self) -> Summary:
        return summarize([t.pnl for t in self.trades])

    @property
    def break_even_hit_rate(self) -> float:
        """Hit rate at which expected P&L is zero after fees."""
        c = self.config
        return c.entry_price * (1 + c.fee_rate)


def _pnl(won: bool, cfg: BacktestConfig) -> float:
    shares = cfg.stake / cfg.entry_price
    return (shares if won else 0.0) - cfg.stake - cfg.stake * cfg.fee_rate


@dataclass
class _Pending:
    window_start: float
    side: Side
    reference_price: float


def run_backtest(
    trades: Iterable[Trade],
    strategy: Strategy,
    config: BacktestConfig | None = None,
    buffer_size: int = 5000,
) -> BacktestResult:
    cfg = config or BacktestConfig()
    if not (0.0 < cfg.entry_price < 1.0):
        raise ValueError("entry_price must be in (0, 1)")
    if not (0.0 <= cfg.decide_after_s < cfg.window_s):
        raise ValueError("decide_after_s must be inside the window")

    buf = TickBuffer(buffer_size)
    result = BacktestResult(cfg)
    replay_now = [0.0]
    risk = RiskManager(cfg.starting_bankroll, clock=lambda: replay_now[0]) if cfg.use_risk_manager else None

    window_start: float | None = None
    reference: float | None = None
    decided = False
    pending: _Pending | None = None

    def settle(p: _Pending, settle_price: float) -> None:
        won = (settle_price >= p.reference_price) == (p.side == "UP")
        pnl = _pnl(won, cfg)
        result.trades.append(TradeRecord(p.window_start, p.side, p.reference_price, settle_price, won, pnl))
        replay_now[0] = p.window_start + cfg.window_s
        if risk:
            risk.record(pnl)

    def maybe_decide(at: float) -> None:
        nonlocal decided, pending
        if decided or window_start is None or reference is None:
            return
        decision_ts = window_start + cfg.decide_after_s
        if at < decision_ts:
            return
        decided = True
        replay_now[0] = decision_ts
        if risk and not risk.check().allowed:
            result.skipped_by_risk += 1
            return
        side = strategy(buf, decision_ts)
        if side in ("UP", "DOWN"):
            pending = _Pending(window_start, side, reference)

    for trade in trades:
        ws = math.floor(trade.ts / cfg.window_s) * cfg.window_s
        if window_start is None or ws > window_start:
            # Close the previous window using only data seen so far.
            if window_start is not None:
                maybe_decide(window_start + cfg.window_s)
                if pending is not None:
                    settle(pending, buf.price_at_or_before(window_start + cfg.window_s))
                    pending = None
            window_start = ws
            reference = buf.last.price if buf.last else None
            decided = False
            result.windows_seen += 1
        # Decide before this trade is visible if the decision time has passed.
        maybe_decide(trade.ts)
        buf.add(trade)
        if reference is None:
            reference = trade.price

    # The final window is incomplete, so it is never settled.
    return result
