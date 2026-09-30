"""Pure parsers for raw WebSocket frames.

Kept free of I/O so they can be tested against canned frames and reused by
both the live stream and offline replay.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pmresearch.models import BookSnapshot, Trade

log = logging.getLogger(__name__)


def parse_binance_agg_trade(msg: dict[str, Any]) -> Trade | None:
    """Parse a Binance ``aggTrade`` event.

    Example: ``{"e":"aggTrade","s":"BTCUSDT","p":"71234.50","q":"0.5","T":1700000000000,"m":true}``
    ``m=True`` means the buyer was the maker, so the aggressor sold.
    Returns ``None`` for subscription acks, other event types, or bad data.
    """
    if msg.get("e") != "aggTrade":
        return None
    try:
        price = float(msg["p"])
        qty = float(msg["q"])
        ts = int(msg["T"]) / 1000.0
    except (KeyError, TypeError, ValueError):
        log.debug("unparseable aggTrade: %r", msg)
        return None
    if price <= 0 or qty < 0:
        return None
    return Trade(
        ts=ts,
        price=price,
        qty=qty,
        symbol=str(msg.get("s", "")).upper(),
        side="sell" if msg.get("m") else "buy",
    )


def _levels(raw: Any, *, descending: bool) -> tuple[tuple[float, float], ...]:
    out: list[tuple[float, float]] = []
    for level in raw or []:
        try:
            price, size = float(level["price"]), float(level["size"])
        except (KeyError, TypeError, ValueError):
            continue
        if 0.0 <= price <= 1.0 and size > 0:
            out.append((price, size))
    out.sort(key=lambda lv: lv[0], reverse=descending)
    return tuple(out)


def parse_polymarket_book(msg: dict[str, Any]) -> BookSnapshot | None:
    """Parse one Polymarket CLOB ``market`` channel book message.

    Levels arrive as ``{"price": "0.48", "size": "120"}`` strings in no
    guaranteed order, so they are sorted here (bids high→low, asks low→high).
    """
    if msg.get("type") == "error" or msg.get("event_type") not in (None, "book"):
        return None
    asset_id = msg.get("asset_id")
    raw_ts = msg.get("timestamp")
    if not asset_id or raw_ts is None:
        return None
    try:
        ts = int(raw_ts) / 1000.0
    except (TypeError, ValueError):
        return None
    return BookSnapshot(
        ts=ts,
        asset_id=str(asset_id),
        bids=_levels(msg.get("bids"), descending=True),
        asks=_levels(msg.get("asks"), descending=False),
        market=str(msg.get("market", "")),
    )


def parse_polymarket_frame(raw: str) -> list[BookSnapshot]:
    """A frame may hold a single object or a list of book messages."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    items = data if isinstance(data, list) else [data]
    books = (parse_polymarket_book(it) for it in items if isinstance(it, dict))
    return [b for b in books if b is not None]
