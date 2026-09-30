import numpy as np
import pytest

from pmresearch.buffer import TickBuffer
from pmresearch.metrics import max_drawdown, summarize, wilson_interval
from pmresearch.models import Trade
from pmresearch.risk import RiskManager, fractional_kelly, kelly_binary
from pmresearch.signals import Regime, classify_regime, directional_efficiency, momentum


def buf_from(prices):
    b = TickBuffer(1000)
    for i, p in enumerate(prices):
        b.add(Trade(float(i), float(p), 1.0))
    return b


def test_momentum_direction():
    assert momentum(buf_from(np.linspace(100, 101, 100))).direction == "UP"
    assert momentum(buf_from(np.linspace(101, 100, 100))).direction == "DOWN"
    assert momentum(buf_from([100.0] * 100)).direction == "NEUTRAL"
    assert momentum(buf_from([100.0] * 10)).direction == "NEUTRAL"  # not enough data


def test_regime_labels():
    assert directional_efficiency(np.array([1.0, 2.0, 3.0])) == 1.0
    assert classify_regime(buf_from(np.linspace(100, 110, 60))) is Regime.TRENDING
    zigzag = [100 + (i % 2) for i in range(60)]
    assert classify_regime(buf_from(zigzag)) is Regime.CHOPPY
    assert classify_regime(buf_from([100.0] * 60)) is Regime.QUIET


def test_kelly_binary():
    assert kelly_binary(0.6, 0.5) == pytest.approx(0.2)
    assert kelly_binary(0.5, 0.5) == 0.0  # no edge
    assert kelly_binary(0.4, 0.5) == 0.0  # negative edge -> no bet
    assert kelly_binary(0.9, 1.0) == 0.0  # invalid price
    assert fractional_kelly(0.99, 0.5) == 0.05  # capped


class FakeClock:
    def __init__(self, t=1_700_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def test_risk_cooldown_after_consecutive_losses():
    clock = FakeClock()
    rm = RiskManager(1000, cooldown_after_losses=3, cooldown_s=600, clock=clock)
    for _ in range(3):
        assert rm.check().allowed
        rm.record(-1)
    assert not rm.check().allowed
    clock.t += 601
    assert rm.check().allowed


def test_risk_daily_cap_and_reset():
    clock = FakeClock(1_700_000_000.0)  # 2023-11-14 22:13 UTC
    rm = RiskManager(100, daily_loss_cap_pct=0.10, cooldown_after_losses=99, clock=clock)
    rm.record(-6)
    rm.record(+1)
    rm.record(-5)
    assert rm.check().reason == "daily loss cap reached"
    clock.t += 3 * 3600  # crosses UTC midnight
    assert rm.check().allowed and rm.daily_pnl == 0.0


def test_metrics():
    assert max_drawdown([1, 1, -3, 1, -1, 5]) == 3
    s = summarize([1.0, -1.0, 1.0, 1.0])
    assert s.trades == 4 and s.wins == 3 and s.hit_rate == 0.75
    assert s.profit_factor == 3.0
    lo, hi = wilson_interval(50, 100)
    assert lo < 0.5 < hi and hi - lo < 0.2
    assert wilson_interval(0, 0) == (0.0, 1.0)
