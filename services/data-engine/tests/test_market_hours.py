from datetime import datetime
from zoneinfo import ZoneInfo

from app.market_hours import is_market_open

IST = ZoneInfo("Asia/Kolkata")


def test_open_during_trading_hours_on_a_weekday():
    assert is_market_open(datetime(2026, 11, 3, 10, 0, tzinfo=IST))  # Tuesday


def test_closed_before_open():
    assert not is_market_open(datetime(2026, 11, 3, 9, 0, tzinfo=IST))


def test_closed_after_close():
    assert not is_market_open(datetime(2026, 11, 3, 15, 45, tzinfo=IST))


def test_closed_on_weekend():
    assert not is_market_open(datetime(2026, 11, 1, 10, 0, tzinfo=IST))  # Sunday


def test_boundary_times_are_inclusive():
    assert is_market_open(datetime(2026, 11, 3, 9, 15, tzinfo=IST))
    assert is_market_open(datetime(2026, 11, 3, 15, 30, tzinfo=IST))
