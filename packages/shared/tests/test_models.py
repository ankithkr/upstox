from datetime import datetime, timezone

from shared.models import Candle, Direction, OrderIntent, Signal, Trade, TradeStatus


def test_candle_roundtrip():
    c = Candle(
        symbol="RELIANCE",
        timeframe="5m",
        open_time=datetime(2026, 1, 2, 9, 15, tzinfo=timezone.utc),
        open=100.0,
        high=101.5,
        low=99.5,
        close=101.0,
        volume=12345,
    )
    assert Candle.model_validate_json(c.model_dump_json()) == c


def test_signal_direction_enum():
    s = Signal(
        id="sig-1",
        symbol="TCS",
        direction=Direction.LONG,
        sector="IT",
        detected_at=datetime.now(timezone.utc),
        breakout_price=100.0,
        stop_price=98.0,
        target_price=106.0,
        filters_passed=["regime_gate", "sector", "stock"],
    )
    assert s.direction == "LONG"


def test_order_intent_requires_risk_amount():
    order = OrderIntent(
        id="ord-1",
        signal_id="sig-1",
        symbol="TCS",
        direction=Direction.LONG,
        qty=10,
        entry_price=100.0,
        stop_price=98.0,
        target_price=106.0,
        risk_amount=20.0,
    )
    assert order.qty * (order.entry_price - order.stop_price) == order.risk_amount


def test_trade_defaults_to_none_until_filled():
    t = Trade(
        id="trd-1",
        order_id="ord-1",
        symbol="TCS",
        direction=Direction.LONG,
        status=TradeStatus.OPEN,
        qty=10,
    )
    assert t.entry_price is None
    assert t.net_pnl is None
