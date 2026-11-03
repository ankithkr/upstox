"""Aggregates live LTP ticks into closed OHLCV candles.

5 minutes divides evenly into the fixed IST/UTC offset (330 min), so
flooring the tick's epoch timestamp to a 300s boundary in UTC lands on
the same wall-clock marks as IST (09:15, 09:20, ...) without needing a
timezone conversion here.
"""

from __future__ import annotations

from datetime import datetime, timezone

from shared.models import Candle


class CandleAggregator:
    def __init__(self, timeframe_seconds: int = 300) -> None:
        self.timeframe_seconds = timeframe_seconds
        self._open_bars: dict[str, Candle] = {}
        self._bucket_start_ms: dict[str, int] = {}

    def ingest_tick(self, symbol: str, price: float, qty: int, tick_time_ms: int) -> Candle | None:
        """Returns the previous candle if this tick starts a new bucket,
        otherwise None (the in-progress bar was just updated)."""
        bucket_ms = self.timeframe_seconds * 1000
        bucket_start_ms = (tick_time_ms // bucket_ms) * bucket_ms

        bar = self._open_bars.get(symbol)
        closed: Candle | None = None

        if bar is None or self._bucket_start_ms[symbol] != bucket_start_ms:
            if bar is not None:
                closed = bar
            bar = Candle(
                symbol=symbol,
                timeframe=f"{self.timeframe_seconds // 60}m",
                open_time=datetime.fromtimestamp(bucket_start_ms / 1000, tz=timezone.utc),
                open=price,
                high=price,
                low=price,
                close=price,
                volume=qty,
            )
            self._bucket_start_ms[symbol] = bucket_start_ms
        else:
            bar = bar.model_copy(
                update={
                    "high": max(bar.high, price),
                    "low": min(bar.low, price),
                    "close": price,
                    "volume": bar.volume + qty,
                }
            )

        self._open_bars[symbol] = bar
        return closed

    def flush(self, symbol: str) -> Candle | None:
        """Force-close the in-progress bar for `symbol` (e.g. at the forced
        15:15/15:30 session end), so the last partial bar isn't lost."""
        return self._open_bars.pop(symbol, None)
