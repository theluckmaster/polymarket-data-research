"""Summary statistics for a sequence of per-trade P&L values."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Summary:
    trades: int
    wins: int
    hit_rate: float
    hit_rate_ci95: tuple[float, float]
    net_pnl: float
    expectancy: float
    max_drawdown: float
    profit_factor: float
    sharpe_per_trade: float


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion.

    Used to ask whether a hit rate is distinguishable from the break-even
    rate, instead of reading a point estimate from a small sample.
    """
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def max_drawdown(pnls: list[float]) -> float:
    """Largest peak-to-trough fall of cumulative P&L (positive number)."""
    peak = equity = worst = 0.0
    for p in pnls:
        equity += p
        peak = max(peak, equity)
        worst = max(worst, peak - equity)
    return worst


def sharpe_per_trade(pnls: list[float]) -> float:
    """Mean / sample std of per-trade P&L. Deliberately not annualised."""
    if len(pnls) < 2:
        return 0.0
    mean = sum(pnls) / len(pnls)
    var = sum((p - mean) ** 2 for p in pnls) / (len(pnls) - 1)
    return mean / math.sqrt(var) if var > 0 else 0.0


def summarize(pnls: list[float]) -> Summary:
    n = len(pnls)
    wins = sum(1 for p in pnls if p > 0)
    gross_win = sum(p for p in pnls if p > 0)
    gross_loss = -sum(p for p in pnls if p < 0)
    pf = gross_win / gross_loss if gross_loss > 0 else (math.inf if gross_win > 0 else 0.0)
    return Summary(
        trades=n,
        wins=wins,
        hit_rate=wins / n if n else 0.0,
        hit_rate_ci95=wilson_interval(wins, n),
        net_pnl=sum(pnls),
        expectancy=sum(pnls) / n if n else 0.0,
        max_drawdown=max_drawdown(pnls),
        profit_factor=pf,
        sharpe_per_trade=sharpe_per_trade(pnls),
    )


def format_summary(s: Summary, break_even: float | None = None) -> str:
    lo, hi = s.hit_rate_ci95
    lines = [
        f"trades           {s.trades}",
        f"hit rate         {s.hit_rate:.1%}  (95% CI {lo:.1%} - {hi:.1%})",
    ]
    if break_even is not None:
        verdict = "above" if lo > break_even else "NOT distinguishable from"
        lines.append(f"break-even rate  {break_even:.1%}  -> CI lower bound {verdict} break-even")
    lines += [
        f"net P&L          {s.net_pnl:+.2f} (units staked: 1 per trade)",
        f"expectancy       {s.expectancy:+.4f} per trade",
        f"max drawdown     {s.max_drawdown:.2f}",
        f"profit factor    {s.profit_factor:.2f}",
        f"sharpe/trade     {s.sharpe_per_trade:.3f}",
    ]
    return "\n".join(lines)
