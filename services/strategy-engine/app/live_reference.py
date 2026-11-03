"""Live-day equivalents of features.DailyIndex / VolumeProfile's lookups.

features.py (ported verbatim from the backtest) always looks a day up
by exact date match in an already-closed series - correct when
backtesting a day that's already in the cache, wrong for "today" while
it's still live and hasn't produced a closed daily candle yet.

Each function here is the same math, anchored at the END of the cached
series (i.e. "as of the most recent close") instead of at a `day`
looked up by bisect. For a day that IS already in the cache, calling
the live function on it and the ported batch function on it agree
exactly; the live function just also works for a day not yet present.
"""

from __future__ import annotations

from .features import DailyIndex, VolumeProfile

LOOKBACK = VolumeProfile.LOOKBACK
MIN_HISTORY = VolumeProfile.MIN_HISTORY


def latest_close(daily: DailyIndex) -> float | None:
    return daily.candles[-1][4] if daily.candles else None


def latest_trend_pct(daily: DailyIndex, window: int = 20) -> float | None:
    if len(daily.candles) < window:
        return None
    closes = [c[4] for c in daily.candles[-window:]]
    return 100 * (closes[-1] / (sum(closes) / window) - 1)


def latest_atr_pct(daily: DailyIndex, window: int = 14) -> float | None:
    if len(daily.candles) < window + 1:
        return None
    rows = daily.candles[-window:]
    prevs = daily.candles[-window - 1 : -1]
    true_ranges = [max(r[2] - r[3], abs(r[2] - p[4]), abs(r[3] - p[4])) for r, p in zip(rows, prevs)]
    return 100 * (sum(true_ranges) / window) / daily.candles[-1][4]


def live_opening_volume_ratio(profile: VolumeProfile, today_opening_volume: float) -> float | None:
    prior_days = [d for d in profile.days[-LOOKBACK:] if d in profile._opening]
    if len(prior_days) < MIN_HISTORY:
        return None
    base = sum(profile._opening[d] for d in prior_days) / len(prior_days)
    return today_opening_volume / base if base else None


def live_slot_volume_ratio(profile: VolumeProfile, timestamp: str, today_slot_volume: float) -> float | None:
    slot = timestamp[11:16]
    prior = [profile._slot_volumes(d).get(slot) for d in profile.days[-LOOKBACK:]]
    prior = [v for v in prior if v is not None]
    if len(prior) < MIN_HISTORY:
        return None
    base = sum(prior) / len(prior)
    return today_slot_volume / base if base else None
