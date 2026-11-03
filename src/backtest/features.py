"""Per-instrument features derived from the candle history (all look-back only)."""

from bisect import bisect_left


class DailyIndex:
    """Prior-day lookups on a daily candle series. Every method uses only data before `day`."""

    def __init__(self, candles: list[tuple]):
        self.candles = candles
        self.dates = [c[0][:10] for c in candles]

    def pos(self, day: str):
        i = bisect_left(self.dates, day)
        return i if i < len(self.dates) and self.dates[i] == day else None

    def prev_close(self, day: str):
        i = self.pos(day)
        return self.candles[i - 1][4] if i else None

    def trend_pct(self, day: str, window: int = 20):
        """Previous close vs the mean of the `window` closes ending there, in %."""
        i = self.pos(day)
        if not i or i < window:
            return None
        closes = [c[4] for c in self.candles[i - window : i]]
        return 100 * (closes[-1] / (sum(closes) / window) - 1)

    def atr_pct(self, day: str, window: int = 14):
        """Average true range of the last `window` sessions as % of the previous close."""
        i = self.pos(day)
        if not i or i < window + 1:
            return None
        rows = self.candles[i - window : i]
        prevs = self.candles[i - window - 1 : i - 1]
        true_ranges = [max(r[2] - r[3], abs(r[2] - p[4]), abs(r[3] - p[4])) for r, p in zip(rows, prevs)]
        return 100 * (sum(true_ranges) / window) / self.candles[i - 1][4]


class VolumeProfile:
    """Relative volume of a stock vs its own recent norm.

    `opening_ratio(day)`: first-three-candle volume vs the mean of the
    previous 20 sessions' first-three-candle volume.
    `slot_ratio(day, ts)`: one candle's volume vs the same time-of-day
    candle's mean over the previous 20 sessions.
    Both need >= 10 prior sessions and return None otherwise.
    """

    LOOKBACK, MIN_HISTORY = 20, 10

    def __init__(self, candles_by_day: dict[str, list[tuple]]):
        self.by_day = candles_by_day
        self.days = sorted(candles_by_day)
        self._opening = {d: sum(c[5] for c in cs[:3]) for d, cs in candles_by_day.items() if len(cs) >= 3}
        self._slots: dict[str, dict[str, float]] = {}

    def _prior_days(self, day: str, usable) -> list[str]:
        i = bisect_left(self.days, day)
        return [d for d in self.days[max(0, i - self.LOOKBACK) : i] if usable(d)]

    def opening_ratio(self, day: str):
        if day not in self._opening:
            return None
        prior = self._prior_days(day, lambda d: d in self._opening)
        if len(prior) < self.MIN_HISTORY:
            return None
        base = sum(self._opening[d] for d in prior) / len(prior)
        return self._opening[day] / base if base else None

    def _slot_volumes(self, day: str) -> dict[str, float]:
        if day not in self._slots:
            self._slots[day] = {c[0][11:16]: c[5] for c in self.by_day[day]}
        return self._slots[day]

    def slot_ratio(self, day: str, timestamp: str):
        slot = timestamp[11:16]
        today = self._slot_volumes(day).get(slot)
        if today is None:
            return None
        prior = [self._slot_volumes(d).get(slot) for d in self._prior_days(day, lambda d: True)]
        prior = [v for v in prior if v is not None]
        if len(prior) < self.MIN_HISTORY:
            return None
        base = sum(prior) / len(prior)
        return today / base if base else None
