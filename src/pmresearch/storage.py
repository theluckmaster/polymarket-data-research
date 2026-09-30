"""JSONL recording and replay.

Files rotate by the *record's* UTC date rather than the wall clock, so a
replayed or backfilled stream lands in the same files a live one would.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Self

from pmresearch.models import Trade


class JsonlWriter:
    """Append records to ``{base_dir}/{series}/{YYYY-MM-DD}.jsonl``."""

    def __init__(self, base_dir: Path | str) -> None:
        self._base = Path(base_dir)
        self._handles: dict[str, tuple[str, IO[str]]] = {}

    def write(self, series: str, ts: float, record: dict) -> None:
        if not series.replace("-", "").replace("_", "").isalnum():
            raise ValueError(f"unsafe series name: {series!r}")  # no path traversal
        day = datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d")
        current = self._handles.get(series)
        if current is None or current[0] != day:
            if current is not None:
                current[1].close()
            path = self._base / series / f"{day}.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            current = (day, path.open("a", encoding="utf-8"))
            self._handles[series] = current
        current[1].write(json.dumps(record, separators=(",", ":")) + "\n")

    def write_trade(self, trade: Trade, series: str | None = None) -> None:
        self.write(series or trade.symbol.lower() or "trades", trade.ts, asdict(trade))

    def close(self) -> None:
        for _, fh in self._handles.values():
            fh.close()
        self._handles.clear()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def read_trades(path: Path | str) -> Iterator[Trade]:
    """Replay trades written by :meth:`JsonlWriter.write_trade`.

    Blank or truncated lines (e.g. from a crash mid-write) are skipped.
    """
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                yield Trade(**row)
            except (json.JSONDecodeError, TypeError):
                continue
