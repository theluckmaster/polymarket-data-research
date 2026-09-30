# polymarket-data-research

Tools for studying short-horizon crypto "UP/DOWN" prediction markets:

- **Streaming ingestion:** a read-only WebSocket client for public trade data, with reconnect, backoff, and stale-feed detection
- **Parsers:** pure parsers for exchange trades and prediction-market order books
- **Rolling features:** a bounded ring buffer (VWAP, EMA, rate of change, volatility) and regime labels
- **Backtester:** a window-based replay that is built so a strategy cannot see future data, with risk controls and honest statistics

**This is a research codebase, not a trading bot.** It contains no order placement, no wallet or signing code, and no API keys. It makes no claim that any signal here is profitable. The included demo shows the opposite: on random data, the harness correctly reports no edge.

## Background

I built a larger private system that recorded Polymarket order books and spot-exchange trades for 5-minute BTC markets and tested strategy ideas against them. This repo is the part worth showing: the data plumbing and the evaluation harness, rewritten as a small, tested package. Live-execution code, account data, and recorded datasets are deliberately excluded (see [SECURITY_AND_DATA_NOTES.md](SECURITY_AND_DATA_NOTES.md)).

The main lesson from that work shaped the design. An early backtester of mine derived the trade direction and the win/loss outcome from the same price move, so every simulated trade won. This version separates the data used to decide from the data used to settle, and tests that separation.

## Quick start (Python 3.11+)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                             # 28 tests, offline, ~1-2 s
python scripts/run_backtest.py     # synthetic null vs. positive control
```

Example output (seed 0, 24 h synthetic data, 2% fee, contract price 0.50):

```
== SYNTHETIC null: driftless random walk  (windows=288, skipped by risk=39)
trades           231
hit rate         51.9%  (95% CI 45.5% - 58.3%)
break-even rate  51.0%  -> CI lower bound NOT distinguishable from break-even
...
== SYNTHETIC positive control: trends persisting 30 min  (windows=288, skipped by risk=0)
trades           272
hit rate         82.4%  (95% CI 77.4% - 86.4%)
break-even rate  51.0%  -> CI lower bound above break-even
```

The null run happens to end with positive P&L, which is exactly why the report leads with a confidence interval against the break-even rate rather than with P&L.

Recording real data (public stream, no key needed):

```bash
python scripts/record_trades.py --symbol btcusdt --minutes 10 --out data/raw
python scripts/record_trades.py --us ...     # Binance.US, if binance.com returns HTTP 451 in your region
python scripts/run_backtest.py --trades data/raw/btcusdt/<date>.jsonl
```

## Layout

```
src/pmresearch/
  models.py     Trade, BookSnapshot (+ mid, spread, depth imbalance)
  parsers.py    Binance aggTrade and Polymarket CLOB book frames -> models (pure)
  stream.py     async public WebSocket client: backoff, stale-feed reconnect, fatal-4xx handling
  storage.py    JSONL writer rotating by record date; tolerant replay reader
  buffer.py     TickBuffer ring buffer with windowed analytics
  signals.py    momentum score and coarse regime classification (research hypotheses)
  risk.py       binary-contract Kelly, fractional Kelly with cap, daily loss cap + cooldown
  metrics.py    hit rate with Wilson CI, drawdown, profit factor, expectancy
  backtest.py   fixed-window replay with structural look-ahead protection
  synthetic.py  seeded random-walk generator (null case and positive control)
scripts/        run_backtest.py, record_trades.py
tests/          28 pytest tests, no network
```

See [architecture.md](architecture.md) for the data flow and design decisions.

## Testing approach

- **Parsers** are tested against hand-written frames, including malformed levels, unsorted books, and acks.
- **The stream client** is tested with a scripted fake connection that drops the connection, goes stale, and is refused. This covers reconnect, backoff reset, fatal-4xx handling, and the rule that programming errors are not swallowed.
- **The backtester** is tested for what it must not do:
  - the strategy never sees a trade later than its decision time
  - it finds no edge on a driftless random walk
  - it does find one on data with a real, planted trend
  - there are also hand-computed settlement cases
- **Risk controls** use an injected clock, so cooldowns and UTC day rollover are tested deterministically.

## Limitations

- The backtester assumes a fixed contract price and fills at that price. It does not replay the recorded prediction-market order book, so slippage and liquidity are not modelled.
- Signals are simple, illustrative features, not tuned strategies.
- Synthetic data demonstrates that the harness is correct. It says nothing about real markets.
