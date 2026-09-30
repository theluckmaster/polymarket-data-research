"""Record public Binance trades to daily JSONL files.

Read-only: connects to the public aggTrade stream, needs no API key, and
places no orders.

    python scripts/record_trades.py --symbol btcusdt --minutes 5 --out data/raw
    python scripts/record_trades.py --us ...   # use Binance.US if binance.com is restricted
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from pmresearch.storage import JsonlWriter
from pmresearch.stream import BINANCE_US_WS_URL, BINANCE_WS_URL, stream_binance_trades

log = logging.getLogger("record_trades")


async def record(symbol: str, minutes: float, out: str, url: str) -> int:
    count = 0

    async def consume(writer: JsonlWriter) -> None:
        nonlocal count
        async for trade in stream_binance_trades([symbol], url=url):
            writer.write_trade(trade)
            count += 1
            if count % 500 == 0:
                log.info("recorded %d trades (last %.2f)", count, trade.price)

    with JsonlWriter(out) as writer:
        try:
            # Enforced by the event loop, so a quiet market can't overrun it.
            await asyncio.wait_for(consume(writer), timeout=minutes * 60)
        except TimeoutError:
            pass
    return count


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbol", default="btcusdt")
    ap.add_argument("--minutes", type=float, default=5.0)
    ap.add_argument("--out", default="data/raw")
    ap.add_argument("--us", action="store_true", help="use the Binance.US public stream")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    n = asyncio.run(
        record(args.symbol, args.minutes, args.out, BINANCE_US_WS_URL if args.us else BINANCE_WS_URL)
    )
    print(f"recorded {n} trades to {args.out}/{args.symbol.lower()}/")


if __name__ == "__main__":
    main()
