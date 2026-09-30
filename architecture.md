# Architecture

## Data flow

```
             live (public, read-only)                     offline
  ┌──────────────────────────────────┐        ┌─────────────────────────┐
  │ stream.stream_binance_trades     │        │ storage.read_trades     │
  │  connect → subscribe → recv loop │        │  JSONL replay           │
  │  stale timeout → reconnect       │        │ synthetic.random_walk_* │
  │  backoff 1→2→4…30 s, fatal 4xx   │        └────────────┬────────────┘
  └───────────────┬──────────────────┘                     │
                  │ raw frames                             │ Trade
          parsers.parse_* (pure)                           │
                  │ Trade / BookSnapshot                   │
        ┌─────────┴─────────┐                              │
        ▼                   ▼                              ▼
  storage.JsonlWriter   buffer.TickBuffer  ◀──────── backtest.run_backtest
  {series}/{date}.jsonl   ring buffer          window roll → decide → settle
                           │                           │         │
                           ▼                           ▼         ▼
                     signals.momentum         risk.RiskManager  metrics.summarize
                     signals.classify_regime  (replay clock)    Wilson CI vs break-even
```

## Design decisions

**Parse at the boundary, then use plain types.** Raw frames become `Trade`/`BookSnapshot` in one pure module, and timestamps become epoch floats once. Everything downstream is I/O-free and testable with literals.

**Injectable I/O.**
- `stream_binance_trades` takes `connect` and `sleep` functions.
- `RiskManager` takes a `clock`.
- Tests therefore run offline and deterministically, and the risk controls run on replay time inside the backtester without modification.

**Stale-feed detection.** A half-open TCP connection can look healthy while delivering nothing. Each `recv` is wrapped in a timeout, so a silent feed is treated as dead and reconnected. Backoff resets after a successful subscribe, so a feed that flaps once an hour doesn't slowly climb to the 30-second ceiling.

**Retry only what can succeed.**
- Network errors, timeouts, and 429s are retried.
- A 4xx handshake rejection such as 451 (region-restricted) raises `FeedRejected` immediately.
- Programming errors (for example `KeyError`) are never swallowed by the reconnect loop.

**Record-date file rotation.** `JsonlWriter` picks the file from the record's timestamp, not the wall clock, so a backfill lands in the same files as a live capture. Series names are validated so they can't escape the output directory.

**Bounded memory.** `TickBuffer` is a `deque(maxlen=N)`. Windowed queries walk backwards from the newest tick and stop at the window edge.

## Backtest model

Time is divided into fixed windows aligned to the epoch (default 300 s), mirroring "will BTC be higher in 5 minutes?" markets.

1. **Window start.** The reference price is the last trade at or before the window start.
2. **Decision time** (`start + decide_after_s`).
   - The risk manager is consulted first.
   - The strategy is called with the buffer as it stands. Trades are appended strictly in time order, and the call happens *before* the first trade after the decision time is added.
   - Look-ahead is therefore impossible by construction, not just by convention, and a test asserts it.
3. **Window end.** The settlement price is the last trade at or before the window end. The window resolves UP if settle ≥ reference.
4. **P&L.** P&L per unit stake is `1/price − 1 − fee` on a win and `−1 − fee` on a loss. The break-even hit rate is `price × (1 + fee)`.
5. **Reporting.** The report compares the Wilson 95% lower bound of the hit rate with the break-even rate. A point estimate or a positive P&L on a few hundred trades proves little.

### Why a null and a positive control

A backtester that always finds an edge is worse than none. The test suite runs the same momentum strategy on two datasets:

- **A driftless random walk.** No signal can have an edge, so the confidence interval must contain 50%.
- **A walk with trends that persist for 30 minutes.** The same signal should, and does, show an edge.

The first catches look-ahead and settlement bugs. The second shows the harness isn't simply blind.

## Deliberately out of scope

- Order placement, wallets, signing, and account endpoints. This repo cannot trade.
- Order-book replay for fills and slippage. That is the next step (see the README's Limitations section).
- Persistence beyond JSONL. The original system also used SQLite; it wasn't needed to demonstrate the ideas.
