"""Plain data types shared by the feeds, buffers, and backtester.

Timestamps are UTC epoch seconds (float) everywhere. Converting once at the
parse boundary keeps the hot path free of datetime arithmetic.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Trade:
    """One executed trade from a spot exchange feed."""

    ts: float
    price: float
    qty: float
    symbol: str = ""
    side: str = ""  # aggressor side: "buy" or "sell"


@dataclass(frozen=True, slots=True)
class BookSnapshot:
    """Order-book snapshot for one prediction-market outcome token.

    ``bids`` are sorted best (highest) first, ``asks`` best (lowest) first.
    Each level is ``(price, size)``; prices are in [0, 1].
    """

    ts: float
    asset_id: str
    bids: tuple[tuple[float, float], ...]
    asks: tuple[tuple[float, float], ...]
    market: str = ""

    @property
    def best_bid(self) -> float | None:
        return self.bids[0][0] if self.bids else None

    @property
    def best_ask(self) -> float | None:
        return self.asks[0][0] if self.asks else None

    @property
    def mid(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return (self.best_bid + self.best_ask) / 2.0

    @property
    def spread(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return self.best_ask - self.best_bid

    def imbalance(self, levels: int = 5) -> float | None:
        """Depth imbalance over the top *levels*: (bid - ask) / (bid + ask).

        +1 means all resting size is on the bid, -1 all on the ask.
        """
        bid_size = sum(size for _, size in self.bids[:levels])
        ask_size = sum(size for _, size in self.asks[:levels])
        total = bid_size + ask_size
        if total == 0:
            return None
        return (bid_size - ask_size) / total
