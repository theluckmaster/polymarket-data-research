"""Run the momentum signal through the window backtester.

By default this uses synthetic data only: a driftless random walk (the null
case, where no signal should show an edge) and a trending walk (a positive
control). Pass --trades to replay a JSONL file recorded by record_trades.py.

    python scripts/run_backtest.py
    python scripts/run_backtest.py --trades data/raw/btcusdt/2026-09-30.jsonl
"""

from __future__ import annotations

import argparse

from pmresearch.backtest import BacktestConfig, run_backtest
from pmresearch.metrics import format_summary
from pmresearch.signals import momentum
from pmresearch.storage import read_trades
from pmresearch.synthetic import random_walk_trades


def momentum_strategy(buf, now):
    direction = momentum(buf).direction
    return None if direction == "NEUTRAL" else direction


def report(title: str, trades, cfg: BacktestConfig) -> None:
    res = run_backtest(trades, momentum_strategy, cfg)
    print(f"\n== {title}  (windows={res.windows_seen}, skipped by risk={res.skipped_by_risk})")
    print(format_summary(res.summary, break_even=res.break_even_hit_rate))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--trades", help="JSONL file of recorded trades")
    ap.add_argument("--window", type=float, default=300.0, help="window length in seconds")
    ap.add_argument("--entry-price", type=float, default=0.50, help="assumed contract price")
    ap.add_argument("--fee", type=float, default=0.02, help="fee as a fraction of stake")
    ap.add_argument("--hours", type=float, default=24.0, help="synthetic data length")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    cfg = BacktestConfig(window_s=args.window, entry_price=args.entry_price, fee_rate=args.fee)
    print("Assumed fill at a fixed contract price; see backtest.py for all simplifications.")

    if args.trades:
        report(f"replay: {args.trades}", read_trades(args.trades), cfg)
        return

    secs = args.hours * 3600
    report("SYNTHETIC null: driftless random walk", random_walk_trades(secs, seed=args.seed), cfg)
    report(
        "SYNTHETIC positive control: trends persisting 30 min",
        random_walk_trades(secs, seed=args.seed, drift_per_s=3e-5, drift_block_s=1800),
        cfg,
    )


if __name__ == "__main__":
    main()
