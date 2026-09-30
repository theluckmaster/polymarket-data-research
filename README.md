# polymarket-data-research

Tools for studying short-horizon crypto "UP/DOWN" prediction markets:

- **Streaming ingestion:** a read-only WebSocket client for public trade data, with reconnect, backoff, and stale-feed detection
- **Parsers:** pure parsers for exchange trades and prediction-market order books
- **Rolling features:** a bounded ring buffer (VWAP, EMA, rate of change, volatility) and regime labels
- **Backtester:** a window-based replay that is built so a strategy cannot see future data, with risk controls and honest statistics

**This is a research codebase, not a trading bot.** It contains no order placement, no wallet or signing code, and no API keys. It makes no claim that any signal here is profitable. The included demo shows the opposite: on random data, the harness correctly reports no edge.

## Research motivation and approaches tested

This started as a question: can high-frequency market data reveal short-lived pricing or timing gaps in Polymarket's 5- and 15-minute "Will BTC be up or down?" markets? Those markets settle on a spot price, but their odds are set by traders. If spot moves first and the odds catch up a moment later, that delay is measurable.

Over about two months I built a larger private system around that question. It streamed Polymarket order books alongside spot-exchange trades, logged them continuously on a VPS, and ran strategy ideas in backtests, in paper trading, and in a few small, tightly capped live tests.

**Approaches I tested**
- **Latency and lead-lag:** does the market's price react to a spot move measurably late?
- **Fair-value pricing:** estimate the probability of finishing above the window's starting price from spot and recent volatility, then compare it with the order book.
- **Short-horizon momentum** from rolling returns, and a **mean-reversion** variant.
- **Order-book strategies:** quoting inside the spread, and buying both outcomes when their combined ask dipped below the $1 payout.
- **Regime filters:** skip low-volatility, near-the-strike conditions; pause after a run of losses.
- **Sizing and risk:** fractional Kelly with a hard cap, a daily loss limit, and cooldowns.
- **Calibration:** a study of whether resolved market prices matched actual outcome frequencies.

**What happened**

Some early versions looked promising in backtests, paper trading, and small live tests. Most of that did not survive contact with scale:
- Forward tests trailed the backtests. One paper run was stopped by its own kill switch within a day.
- Part of the gap was my own tooling. An early backtester derived trade direction and outcome from the same price move, so every simulated trade won. Later retrospective tests had subtler timestamp-alignment leaks.
- The rest was the market. Prices were well calibrated overall. The latency gaps that did exist lasted fractions of a second and were contested by many faster bots. Competing for them would have needed co-located, sub-100 ms infrastructure and far more capital than a research budget.
- In short, the opportunities that were real were saturated, and the ones that looked open mostly came from how the data was measured.

**What this repo keeps**

This repo is the part worth showing: the data plumbing and the evaluation harness, rewritten as a small, tested package.
- **Ingestion:** streaming WebSocket ingestion with reconnect and stale-feed handling.
- **Features:** rolling tick buffers, momentum scoring, and regime labels.
- **Risk:** risk-limit and sizing primitives.
- **Backtester:** it makes look-ahead impossible by construction.
- **Two safeguard tests:** a random-walk null test that must find *no* edge, and a planted-trend test that must find one. Together they guard against the false conclusions that cost me the most time.

Live-execution code, wallet and API details, account data, and recorded datasets are deliberately excluded (see [SECURITY_AND_DATA_NOTES.md](SECURITY_AND_DATA_NOTES.md)). Nothing here is a profitable strategy or trading advice.

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
