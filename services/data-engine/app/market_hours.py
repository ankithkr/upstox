"""NSE market-hours gate.

TODO: this does not account for NSE trading holidays (Republic Day,
Diwali, etc.) - it will treat those as open days. Needs a real holiday
calendar (NSE publishes one) wired in before this runs unattended;
flagging rather than guessing at a holiday list.
"""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)


def is_market_open(now: datetime | None = None) -> bool:
    now_ist = (now or datetime.now(tz=ZoneInfo("UTC"))).astimezone(IST)
    if now_ist.weekday() >= 5:  # Saturday, Sunday
        return False
    return MARKET_OPEN <= now_ist.time() <= MARKET_CLOSE
