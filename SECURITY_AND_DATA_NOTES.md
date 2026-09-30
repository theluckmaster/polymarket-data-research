# Security and data notes

## What this repository is

A research and data-engineering toolkit. It reads **public** market data and replays it offline.

## What it deliberately does not contain

| Excluded | Why |
|---|---|
| Order placement, order management, market-making loops | Out of scope for a research repo; mistakes cost money |
| Wallets, private keys, transaction signing, on-chain redemption | Never belongs in a public repo, even as placeholders |
| Exchange or Polymarket API keys, account endpoints | Nothing here needs authentication |
| Account data: trade logs, balances, P&L, session logs | Personal financial data |
| Recorded datasets | Large, and redistribution terms vary by source; record your own |
| Alert integrations (Telegram, Discord) and their tokens/webhooks | Not relevant to the research code |
| Performance, win-rate, or profitability claims | None are made; synthetic results only demonstrate harness correctness |

## Provenance

The modules were adapted from my private projects and rewritten for this repo. I copied individual modules into a fresh repository, not the git history of the source projects. Those projects contain execution code and configuration that must stay private.

## Network behaviour

- `scripts/record_trades.py` opens one outbound WebSocket to a public exchange stream and writes JSONL under `data/`. It sends only a subscribe message.
- The test suite makes no network calls.

## Local data hygiene

- `.gitignore` excludes `data/`, `*.jsonl`, `*.csv`, `*.sqlite`, logs, `.env*`, key files, and wallet or keystore patterns.
- The project needs no secrets. If a future change seems to require one, that change belongs in a different, private repository.

## Reporting

If you find something in this repo that looks sensitive, please open an issue without including the value.
