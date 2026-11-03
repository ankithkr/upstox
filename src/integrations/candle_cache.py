"""Read every cached candle chunk for an instrument, whatever range it was fetched for.

`upstox_history.get_candles` caches one CSV per requested chunk, named by
the chunk's own date range, so different fetch runs leave overlapping or
adjacent files. The backtest wants "everything we have", so this globs
all chunks for (instrument, unit, interval), merges them, drops duplicate
timestamps (later-fetched chunks win) and returns the series oldest first.
Never touches the network.
"""

from pathlib import Path

from src.integrations.upstox_history import CACHE_DIR, _read_cache

_MEMO: dict[tuple, list[tuple]] = {}


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
