def value_at_930_from_15m(day_candles_15m: list[tuple]):
    """Close of the first 15-min candle of the day (09:15-09:30)."""
    return day_candles_15m[0][4] if day_candles_15m else None


def value_at_930_from_5m(day_candles_5m: list[tuple]):
    """Close of the third 5-min candle of the day (09:25-09:30)."""
    return day_candles_5m[2][4] if len(day_candles_5m) >= 3 else None


def candles_on_day(candles: list[tuple], day: str) -> list[tuple]:
    return [c for c in candles if c[0].startswith(day)]


def prev_close(daily_candles: list[tuple], day: str):
    """Close of the daily candle immediately before `day`."""
    for i, candle in enumerate(daily_candles):
        if candle[0].startswith(day):
            return daily_candles[i - 1][4] if i > 0 else None
    return None


def trading_days(candles: list[tuple]) -> list[str]:
    """Sorted unique calendar dates (YYYY-MM-DD) present in a candle series."""
    return sorted({c[0][:10] for c in candles})
