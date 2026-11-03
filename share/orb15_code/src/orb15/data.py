"""Load cached 1-minute candles into per-day lists."""
from collections import defaultdict
from datetime import date

from src.integrations.upstox_history import get_candles
from src.orb15.config import ALT_TATA, DAILY_START, END, START, UNIVERSE

# Candle layout after parsing: (minute_of_day, open, high, low, close, volume)
# where minute_of_day = hour*60+minute of the candle START (09:15 -> 555).
OPEN_MIN = 9 * 60 + 15
CLOSE_MIN = 15 * 60 + 30


def hhmm(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def _parse(c):
    ts = c[0]
    return (int(ts[11:13]) * 60 + int(ts[14:16]), c[1], c[2], c[3], c[4], c[5])


def load_symbol(key: str, start: date = START, end: date = END):
    """-> (days: dict[date_str, list[candle]], daily: dict[date_str, (o,h,l,c,v)])."""
    days = defaultdict(list)
    for c in get_candles(key, "minutes", "1", start, end):
        days[c[0][:10]].append(_parse(c))
    daily = {c[0][:10]: tuple(c[1:6]) for c in get_candles(key, "days", "1", DAILY_START, end)}
    return dict(days), daily


def load_all(include_alt: bool = True):
    out = {}
    for sym, key in {**UNIVERSE, **(ALT_TATA if include_alt else {})}.items():
        out[sym] = load_symbol(key)
    return out


def complete_days(days: dict) -> list[str]:
    """Days with the full 375-candle session."""
    return sorted(d for d, cs in days.items() if len(cs) == 375 and cs[0][0] == OPEN_MIN)
