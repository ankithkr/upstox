from datetime import datetime, timezone

from app.sizing import size_order
from shared.models import Direction, Signal


def make_signal(breakout_price=100.0, stop_price=99.0, target_price=103.0) -> Signal:
    return Signal(
        id="sig-1",
        symbol="TCS",
        direction=Direction.LONG,
        sector="NIFTY IT",
        detected_at=datetime.now(timezone.utc),
        breakout_price=breakout_price,
        stop_price=stop_price,
        target_price=target_price,
        filters_passed=[],
    )


def test_risk_limited_sizing():
    # equity=100000, risk_pct=1% -> risk budget=1000; risk/share=1.0 -> qty_by_risk=1000
    # plenty of cash (100000/100=1000) -> cash doesn't bind
    signal = make_signal(breakout_price=100.0, stop_price=99.0)
    result = size_order(signal, equity=100_000, cash=100_000, risk_pct=1.0, leverage=1.0)
    assert not result.skipped
    assert result.qty == 1000
    assert result.risk_amount == 1000.0


def test_cash_limited_sizing():
    # risk budget huge (equity=1,000,000 at 1%=10000, risk/share=1.0 -> qty_by_risk=10000)
    # but only 5000 cash at price 100 -> qty_by_cash=50
    signal = make_signal(breakout_price=100.0, stop_price=99.0)
    result = size_order(signal, equity=1_000_000, cash=5_000, risk_pct=1.0, leverage=1.0)
    assert not result.skipped
    assert result.qty == 50


def test_skipped_when_zero_risk_per_share():
    signal = make_signal(breakout_price=100.0, stop_price=100.0)
    result = size_order(signal, equity=100_000, cash=100_000, risk_pct=1.0, leverage=1.0)
    assert result.skipped
    assert result.skip_reason == "zero risk per share"
    assert result.qty == 0


def test_skipped_when_risk_per_share_exceeds_budget():
    # risk budget = 100000*1%=1000; risk/share=2000 -> qty_by_risk=0
    signal = make_signal(breakout_price=5000.0, stop_price=3000.0)
    result = size_order(signal, equity=100_000, cash=100_000, risk_pct=1.0, leverage=1.0)
    assert result.skipped
    assert "risk budget" in result.skip_reason


def test_skipped_when_no_cash_left():
    signal = make_signal(breakout_price=100.0, stop_price=99.0)
    result = size_order(signal, equity=100_000, cash=50, risk_pct=1.0, leverage=1.0)
    assert result.skipped
    assert "cash" in result.skip_reason


def test_leverage_multiplies_buying_power():
    signal = make_signal(breakout_price=100.0, stop_price=99.0)
    unleveraged = size_order(signal, equity=1_000_000, cash=1000, risk_pct=1.0, leverage=1.0)
    leveraged = size_order(signal, equity=1_000_000, cash=1000, risk_pct=1.0, leverage=2.0)
    assert leveraged.qty == unleveraged.qty * 2
