import asyncio
import json

import pytest

from pmresearch.models import Trade
from pmresearch.storage import JsonlWriter, read_trades
from pmresearch.stream import FeedRejected, stream_binance_trades


def agg(ts_ms, price):
    return json.dumps({"e": "aggTrade", "s": "BTCUSDT", "p": str(price), "q": "1", "T": ts_ms, "m": False})


class FakeConn:
    """Scripted connection: returns frames, then raises the given error."""

    def __init__(self, frames, error):
        self.frames = list(frames)
        self.error = error
        self.sent = []
        self.closed = False

    async def send(self, msg):
        self.sent.append(json.loads(msg))

    async def recv(self):
        if self.frames:
            return self.frames.pop(0)
        raise self.error

    async def close(self):
        self.closed = True


def test_stream_parses_reconnects_and_backs_off():
    conns = [
        FakeConn([agg(1000, 1), '{"result":null,"id":1}', "garbage", agg(2000, 2)], ConnectionError("drop")),
        FakeConn([agg(3000, 3)], TimeoutError()),
        FakeConn([], OSError("refused")),
    ]
    made, sleeps = [], []

    async def connect(url):
        made.append(conns[len(made)])
        return made[-1]

    async def fake_sleep(s):
        sleeps.append(s)

    async def collect():
        return [
            t
            async for t in stream_binance_trades(
                ["BTCUSDT"], connect=connect, sleep=fake_sleep, max_reconnects=2
            )
        ]

    trades = asyncio.run(collect())
    assert [t.price for t in trades] == [1, 2, 3]
    assert made[0].sent[0]["params"] == ["btcusdt@aggTrade"]
    assert all(c.closed for c in made)
    # backoff resets after each successful subscribe, so every retry waits 1s
    assert sleeps == [1.0, 1.0]


def test_stream_does_not_swallow_programming_errors():
    async def connect(url):
        return FakeConn([], KeyError("bug"))

    async def run():
        async for _ in stream_binance_trades(["x"], connect=connect):
            pass

    with pytest.raises(KeyError):
        asyncio.run(run())


def test_writer_rotates_by_record_date_and_round_trips(tmp_path):
    day1 = Trade(1_700_000_000.0, 100.0, 1.0, "BTCUSDT", "buy")  # 2023-11-14
    day2 = Trade(1_700_100_000.0, 101.0, 2.0, "BTCUSDT", "sell")  # 2023-11-16
    with JsonlWriter(tmp_path) as w:
        w.write_trade(day1)
        w.write_trade(day2)
    files = sorted(p.name for p in (tmp_path / "btcusdt").iterdir())
    assert files == ["2023-11-14.jsonl", "2023-11-16.jsonl"]
    (tmp_path / "btcusdt" / "2023-11-14.jsonl").open("a").write('{"truncated": \n\n')
    assert list(read_trades(tmp_path / "btcusdt" / "2023-11-14.jsonl")) == [day1]


def test_writer_rejects_path_traversal(tmp_path):
    with pytest.raises(ValueError):
        JsonlWriter(tmp_path).write("../escape", 0.0, {})


class _Rejected(OSError):
    def __init__(self, status):
        super().__init__(f"HTTP {status}")
        self.status_code = status


def test_stream_gives_up_on_geo_block_but_retries_rate_limit():
    async def run(status):
        attempts = []

        async def connect(url):
            attempts.append(url)
            raise _Rejected(status)

        async def no_sleep(s):
            pass

        async for _ in stream_binance_trades(["x"], connect=connect, sleep=no_sleep, max_reconnects=3):
            pass
        return attempts

    with pytest.raises(FeedRejected):
        asyncio.run(run(451))
    assert len(asyncio.run(run(429))) == 4  # retryable: 1 attempt + 3 reconnects
