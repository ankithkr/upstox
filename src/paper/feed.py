"""Candle sources for the paper engine.

The engine only ever talks to a Feed, so the same code runs live (Upstox
intraday API) and in replay (the local candle cache) - which is how the
engine is validated against the backtest without needing a live market.
"""

from collections import defaultdict
from datetime import date, timedelta

from src.integrations.upstox_history import get_candles
from src.integrations.upstox_instruments import build_equity_symbol_index, load_instrument_master

DAILY_LOOKBACK_DAYS = 10


def prev_close_before(daily_candles: list[tuple], day: str):
    """Close of the last daily candle strictly before `day` (YYYY-MM-DD)."""
    prior = [c for c in daily_candles if c[0][:10] < day]
    return prior[-1][4] if prior else None


class _Feed:
    def __init__(self):
        self._symbol_key = None

    def symbol_key(self, symbol: str):
        if self._symbol_key is None:
            self._symbol_key = build_equity_symbol_index(load_instrument_master())
        return self._symbol_key.get(symbol)


class ReplayFeed(_Feed):
    """Serves a past day's candles from the local cache (no network)."""

    def __init__(self, start: date, end: date):
        super().__init__()
        self._start, self._end = start, end
        self._by_day: dict[tuple, dict[str, list]] = {}
        self._daily: dict[str, list] = {}

    def candles(self, key, unit, interval, day):
        series_key = (key, unit, interval)
        if series_key not in self._by_day:
            grouped = defaultdict(list)
            for c in get_candles(key, unit, interval, self._start, self._end):
                grouped[c[0][:10]].append(c)
            self._by_day[series_key] = grouped
        return self._by_day[series_key].get(day, [])

    def prev_close(self, key, day):
        if key not in self._daily:
            daily_start = self._start - timedelta(days=DAILY_LOOKBACK_DAYS)
            self._daily[key] = get_candles(key, "days", "1", daily_start, self._end)
        return prev_close_before(self._daily[key], day)


class LiveFeed(_Feed):
    """Today's candles straight from Upstox's intraday endpoint."""

    def __init__(self):
        super().__init__()
        self._prev: dict[tuple, float | None] = {}

    def candles(self, key, unit, interval, day):
        from src.integrations.upstox_intraday import get_intraday_candles

        return [c for c in get_intraday_candles(key, unit, interval) if c[0][:10] == day]

    def prev_close(self, key, day):
        if (key, day) not in self._prev:
            end = date.fromisoformat(day) - timedelta(days=1)
            daily = get_candles(key, "days", "1", end - timedelta(days=DAILY_LOOKBACK_DAYS), end)
            self._prev[(key, day)] = prev_close_before(daily, day)
        return self._prev[(key, day)]
