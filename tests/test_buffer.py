import math
from itertools import pairwise

import pytest

from pmresearch.buffer import TickBuffer
from pmresearch.models import Trade


def fill(prices, start=0.0, step=1.0, qty=1.0, size=100):
    buf = TickBuffer(size)
    for i, p in enumerate(prices):
        buf.add(Trade(start + i * step, p, qty))
    return buf


def test_eviction_keeps_newest():
    buf = fill(range(1, 11), size=3)
    assert buf.size == 3
    assert [t.price for t in buf.last_n(10)] == [8, 9, 10]


def test_rejects_out_of_order():
    buf = fill([1, 2])
    with pytest.raises(ValueError):
        buf.add(Trade(0.5, 3, 1))


def test_vwap_window():
    buf = TickBuffer(10)
    buf.add(Trade(0, 100, 1))
    buf.add(Trade(5, 110, 3))
    buf.add(Trade(10, 120, 1))
    assert buf.vwap(5) == pytest.approx((110 * 3 + 120) / 4)
    assert buf.vwap(100) == pytest.approx((100 + 330 + 120) / 5)


def test_rate_of_change_uses_past_price():
    buf = fill([100, 101, 102, 103, 104, 110])  # ts 0..5
    assert buf.rate_of_change(5) == pytest.approx(0.10)
    assert buf.rate_of_change(1000) is None  # nothing that old


def test_price_at_or_before():
    buf = fill([10, 20, 30])
    assert buf.price_at_or_before(1.5) == 20
    assert buf.price_at_or_before(-1) is None


def test_ema_constant_series():
    assert fill([50.0] * 20).ema(10) == pytest.approx(50.0)


def test_volatility_matches_log_return_std():
    prices = [100, 101, 99, 102, 100]
    lr = [math.log(b / a) for a, b in pairwise(prices)]
    mean = sum(lr) / len(lr)
    expected = math.sqrt(sum((x - mean) ** 2 for x in lr) / (len(lr) - 1))
    assert fill(prices).volatility(5) == pytest.approx(expected)
    assert fill([100, 101]).volatility(5) is None
