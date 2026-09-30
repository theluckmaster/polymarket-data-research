"""The backtester's job is to *not* manufacture an edge.

These tests check that it (1) never shows the strategy future data,
(2) finds no edge in a driftless random walk, and (3) does find one when the
data genuinely contains it.
"""

import pytest

from pmresearch.backtest import BacktestConfig, run_backtest
from pmresearch.models import Trade
from pmresearch.signals import momentum
from pmresearch.synthetic import random_walk_trades

CFG = BacktestConfig(window_s=300, entry_price=0.5, fee_rate=0.0, use_risk_manager=False)


def momentum_strategy(buf, now):
    sig = momentum(buf)
    return sig.direction if sig.direction != "NEUTRAL" else None


def test_strategy_never_sees_future_trades():
    trades = random_walk_trades(3600, seed=1)
    seen = []

    def spy(buf, now):
        assert buf.last is None or buf.last.ts <= now
        seen.append(now)
        return "UP"

    run_backtest(trades, spy, BacktestConfig(decide_after_s=60, use_risk_manager=False))
    assert seen and all(t % 300 == 60 for t in seen)


def test_settlement_by_hand():
    # window [0,300): ref=100 (first trade), settles at 105 -> UP wins
    # window [300,600): ref=105 (last before 300), settles at 90 -> UP loses
    trades = [Trade(t, p, 1) for t, p in [(0, 100), (100, 105), (350, 90), (650, 91)]]
    res = run_backtest(trades, lambda b, n: "UP", CFG)
    assert [(r.reference_price, r.settle_price, r.won) for r in res.trades] == [
        (100, 105, True),
        (105, 90, False),
    ]
    assert [r.pnl for r in res.trades] == [1.0, -1.0]  # stake 1 at 0.50


def test_no_edge_on_random_walk():
    trades = random_walk_trades(6 * 3600 * 4, seed=7)  # ~290 windows
    s = run_backtest(trades, momentum_strategy, CFG).summary
    assert s.trades > 200
    lo, hi = s.hit_rate_ci95
    assert lo < 0.5 < hi, f"harness found a fake edge: {s.hit_rate:.3f}"


def test_detects_real_edge_in_trending_data():
    trades = random_walk_trades(6 * 3600 * 4, seed=7, drift_per_s=3e-5, drift_block_s=1800)
    s = run_backtest(trades, momentum_strategy, CFG).summary
    assert s.hit_rate_ci95[0] > 0.5


def test_fees_raise_break_even_and_risk_manager_skips():
    cfg = BacktestConfig(entry_price=0.5, fee_rate=0.02, use_risk_manager=True, starting_bankroll=10)
    res = run_backtest(random_walk_trades(12 * 3600, seed=3), lambda b, n: "DOWN", cfg)
    assert res.break_even_hit_rate == pytest.approx(0.51)
    assert res.skipped_by_risk > 0  # cap or cooldown engaged on a small bankroll


def test_rejects_bad_config():
    with pytest.raises(ValueError):
        run_backtest([], momentum_strategy, BacktestConfig(entry_price=1.0))
