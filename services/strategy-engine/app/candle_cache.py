"""Read every cached candle chunk for an instrument, whatever range it was
fetched for. Ported from the legacy src/integrations/candle_cache.py +
src/integrations/upstox_history.py (the cache-reading half only -
strategy-engine never fetches from Upstox itself, only reads the
existing data_cache/ built by the legacy fetch_history.py/refresh_cache.py
flow, mounted read-only).

`get_candles` caches one CSV per requested chunk, named by the chunk's
own date range, so different fetch runs leave overlapping or adjacent
files. This globs all chunks for (instrument, unit, interval), merges
them, drops duplicate timestamps (later-fetched chunks win) and returns
the series oldest first. Never touches the network.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path

CACHE_DIR = Path(os.environ.get("CANDLE_CACHE_DIR", "data_cache/candles"))

_MEMO: dict[tuple, list[tuple]] = {}


def _read_cache(path: Path) -> list[tuple] | None:
    if not path.exists():
        return None
    with open(path, newline="") as f:
        reader = csv.reader(f)
        next(reader)
        return [
            (row[0], float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5]))
            for row in reader
        ]


def read_cached(instrument_key: str, unit: str, interval: str, cache_dir: Path = CACHE_DIR) -> list[tuple]:
    memo_key = (instrument_key, unit, interval, str(cache_dir))
    if memo_key in _MEMO:
        return _MEMO[memo_key]

    safe_key = "".join(c if c.isalnum() else "_" for c in instrument_key)
    prefix = f"{safe_key}_{unit}_{interval}_"
    files = []
    for path in Path(cache_dir).glob(f"{prefix}*.csv"):
        parts = path.stem[len(prefix):].split("_")
        if len(parts) == 2:  # exactly "<from>_<to>": rules out longer keys sharing the prefix
            files.append((parts[1], parts[0], path))
    files.sort()  # by chunk end date, then start

    merged: dict[str, tuple] = {}
    for _end, _start, path in files:
        for candle in _read_cache(path) or []:
            merged[candle[0]] = candle
    result = [merged[ts] for ts in sorted(merged)]
    _MEMO[memo_key] = result
    return result
