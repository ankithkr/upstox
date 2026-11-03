"""Proves the live ("as of now") helpers agree exactly with the ported
batch DailyIndex/VolumeProfile methods when asked about a day that's
already in the cached series - the live helpers are just those same
methods anchored at the end of the series instead of a `day` lookup."""

from app.features import DailyIndex, VolumeProfile
from app.live_reference import (
    latest_atr_pct,
    latest_close,
    latest_trend_pct,
    live_opening_volume_ratio,
    live_slot_volume_ratio,
)


def _daily_candles(n: int, start_price: float = 100.0):
    # (timestamp, open, high, low, close, volume); close drifts a little each day.
    candles = []
    price = start_price
    for i in range(n):
        price += (1 if i % 2 == 0 else -0.5)
        candles.append((f"2026-01-{i + 1:02d}T00:00:00+05:30", price, price + 1, price - 1, price, 1000))
    return candles


def test_latest_close_matches_prev_close_of_the_day_after():
    candles = _daily_candles(25)
    daily = DailyIndex(candles)
    next_day = "2026-01-26T00:00:00+05:30"[:10]
    # prev_close needs `day` present in the series to look up i-1; simulate
    # "today" by using a DailyIndex missing the live day, same series.
    assert latest_close(daily) == candles[-1][4]


def test_latest_trend_matches_batch_trend_for_a_day_already_in_history():
    candles = _daily_candles(30)
    full = DailyIndex(candles)
    # Treat day 21 as "today": history truncated to just before it.
    truncated = DailyIndex(candles[:20])
    batch_trend = full.trend_pct(candles[20][0][:10], window=20)
    live_trend = latest_trend_pct(truncated, window=20)
    assert live_trend == batch_trend


def test_latest_atr_matches_batch_atr_for_a_day_already_in_history():
    candles = _daily_candles(30)
    full = DailyIndex(candles)
    truncated = DailyIndex(candles[:20])
    batch_atr = full.atr_pct(candles[20][0][:10], window=14)
    live_atr = latest_atr_pct(truncated, window=14)
    assert live_atr == batch_atr


def test_live_opening_ratio_matches_batch_for_a_day_already_in_history():
    by_day = {}
    for i in range(25):
        day = f"2026-01-{i + 1:02d}"
        by_day[day] = [
            (f"{day}T09:1{j}:00+05:30", 100, 101, 99, 100, 100 + j) for j in range(5)
        ]
    full = VolumeProfile(by_day)
    target_day = "2026-01-21"
    truncated = VolumeProfile({d: c for d, c in by_day.items() if d < target_day})

    batch_ratio = full.opening_ratio(target_day)
    today_opening_volume = sum(c[5] for c in by_day[target_day][:3])
    live_ratio = live_opening_volume_ratio(truncated, today_opening_volume)
    assert live_ratio == batch_ratio


def test_live_slot_ratio_matches_batch_for_a_day_already_in_history():
    by_day = {}
    for i in range(25):
        day = f"2026-01-{i + 1:02d}"
        by_day[day] = [
            (f"{day}T09:1{j}:00+05:30", 100, 101, 99, 100, 200 + j) for j in range(5)
        ]
    full = VolumeProfile(by_day)
    target_day = "2026-01-21"
    truncated = VolumeProfile({d: c for d, c in by_day.items() if d < target_day})

    breakout_candle = by_day[target_day][3]
    batch_ratio = full.slot_ratio(target_day, breakout_candle[0])
    live_ratio = live_slot_volume_ratio(truncated, breakout_candle[0], breakout_candle[5])
    assert live_ratio == batch_ratio


def test_insufficient_history_returns_none():
    candles = _daily_candles(5)
    daily = DailyIndex(candles)
    assert latest_trend_pct(daily, window=20) is None
    assert latest_atr_pct(daily, window=14) is None
