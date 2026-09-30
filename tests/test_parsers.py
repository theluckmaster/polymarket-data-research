import json

from pmresearch.parsers import (
    parse_binance_agg_trade,
    parse_polymarket_book,
    parse_polymarket_frame,
)

AGG = {"e": "aggTrade", "s": "btcusdt", "p": "71234.50", "q": "0.500", "T": 1_700_000_000_123, "m": True}


def test_binance_agg_trade_fields():
    t = parse_binance_agg_trade(AGG)
    assert t is not None
    assert t.price == 71234.50 and t.qty == 0.5
    assert t.ts == 1_700_000_000.123
    assert t.symbol == "BTCUSDT"
    assert t.side == "sell"  # buyer was maker -> aggressor sold


def test_binance_ignores_acks_and_garbage():
    assert parse_binance_agg_trade({"result": None, "id": 1}) is None
    assert parse_binance_agg_trade({**AGG, "p": "not-a-number"}) is None
    assert parse_binance_agg_trade({**AGG, "p": "0"}) is None
    assert parse_binance_agg_trade({k: v for k, v in AGG.items() if k != "T"}) is None


BOOK = {
    "event_type": "book",
    "asset_id": "123",
    "market": "0xabc",
    "timestamp": "1700000000500",
    # deliberately unsorted, with one bad level and one out-of-range price
    "bids": [{"price": "0.40", "size": "10"}, {"price": "0.48", "size": "5"}, {"price": "x", "size": "1"}],
    "asks": [{"price": "0.55", "size": "7"}, {"price": "0.52", "size": "3"}, {"price": "1.5", "size": "9"}],
}


def test_polymarket_book_sorted_and_cleaned():
    b = parse_polymarket_book(BOOK)
    assert b is not None
    assert b.bids == ((0.48, 5.0), (0.40, 10.0))
    assert b.asks == ((0.52, 3.0), (0.55, 7.0))
    assert b.best_bid == 0.48 and b.best_ask == 0.52
    assert abs(b.mid - 0.50) < 1e-12
    assert abs(b.spread - 0.04) < 1e-12
    assert abs(b.imbalance() - (15 - 10) / 25) < 1e-12


def test_polymarket_frame_list_and_errors():
    frame = json.dumps([BOOK, {"type": "error", "message": "INVALID"}, "junk"])
    assert len(parse_polymarket_frame(frame)) == 1
    assert parse_polymarket_frame("{not json") == []
    assert parse_polymarket_book({**BOOK, "event_type": "price_change"}) is None
