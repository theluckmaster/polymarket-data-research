"""Read-only streaming ingestion from a public exchange WebSocket.

No authentication is used or supported: the Binance ``aggTrade`` stream is
public market data. The connection factory is injectable so reconnect and
stale-feed handling can be tested without a network.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from typing import Any, Protocol

import websockets
from websockets.exceptions import WebSocketException

from pmresearch.models import Trade
from pmresearch.parsers import parse_binance_agg_trade

log = logging.getLogger(__name__)

BINANCE_WS_URL = "wss://stream.binance.com:9443/ws"
BINANCE_US_WS_URL = "wss://stream.binance.us:9443/ws"  # same message format


class FeedRejected(RuntimeError):
    """The server refused the handshake with a non-retryable 4xx status
    (e.g. 451 when an endpoint is geo-restricted). Retrying cannot help."""


def _handshake_status(exc: BaseException) -> int | None:
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None) or getattr(exc, "status_code", None)


class Connection(Protocol):
    async def send(self, message: str) -> None: ...
    async def recv(self) -> str | bytes: ...
    async def close(self) -> None: ...


ConnectFn = Callable[[str], Awaitable[Connection]]


async def _default_connect(url: str) -> Connection:
    return await websockets.connect(url, ping_interval=20, ping_timeout=10)


async def stream_binance_trades(
    symbols: Iterable[str],
    *,
    url: str = BINANCE_WS_URL,
    connect: ConnectFn = _default_connect,
    stale_after_s: float = 15.0,
    max_backoff_s: float = 30.0,
    max_reconnects: int | None = None,
    sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
) -> AsyncIterator[Trade]:
    """Yield trades forever, reconnecting with exponential backoff.

    A feed that goes silent for *stale_after_s* is treated as dead and
    reconnected: a half-open socket otherwise looks healthy while
    delivering nothing. Backoff resets after a successful subscribe.
    """
    params = [f"{s.lower()}@aggTrade" for s in symbols]
    backoff = 1.0
    reconnects = 0

    while True:
        conn: Connection | None = None
        try:
            conn = await connect(url)
            await conn.send(json.dumps({"method": "SUBSCRIBE", "params": params, "id": 1}))
            backoff = 1.0
            log.info("subscribed: %s", ", ".join(params))
            while True:
                raw = await asyncio.wait_for(conn.recv(), timeout=stale_after_s)
                try:
                    msg = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    continue
                if isinstance(msg, dict) and (trade := parse_binance_agg_trade(msg)):
                    yield trade
        except (TimeoutError, OSError, WebSocketException) as exc:
            status = _handshake_status(exc)
            if status is not None and 400 <= status < 500 and status != 429:
                raise FeedRejected(f"{url} rejected the connection: HTTP {status}") from exc
            # TimeoutError here means the feed went stale.
            log.warning("feed lost (%s: %s)", type(exc).__name__, exc)
        finally:
            if conn is not None:
                try:
                    await conn.close()
                except Exception as exc:  # noqa: BLE001 - best-effort close
                    log.debug("close failed: %s", exc)

        reconnects += 1
        if max_reconnects is not None and reconnects > max_reconnects:
            return
        log.info("reconnecting in %.1fs", backoff)
        await sleep(backoff)
        backoff = min(backoff * 2, max_backoff_s)
