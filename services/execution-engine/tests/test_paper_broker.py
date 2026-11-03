import asyncio

from app.brokers.paper_broker import EOD_EXIT, EXPIRED, STOPPED_BREAKEVEN, STOPPED_LOSS, TARGET_HIT, PaperBroker
from shared.models import Direction, OrderIntent, TradeStatus


def make_order(
    direction=Direction.LONG, entry=100.0, stop=98.0, target=106.0, breakeven_trigger=102.0, qty=10
) -> OrderIntent:
    return OrderIntent(
        id="ord-1",
        signal_id="sig-1",
        symbol="TCS",
        direction=direction,
        qty=qty,
        entry_price=entry,
        stop_price=stop,
        target_price=target,
        breakeven_trigger=breakeven_trigger,
        risk_amount=qty * abs(entry - stop),
    )


def candle(ts, o, h, l, c, v=1000):
    return (ts, o, h, l, c, v)


def place(broker, order):
    return asyncio.run(broker.place_order(order))


def test_pending_until_entry_touched():
    broker = PaperBroker()
    order = make_order()
    trade = place(broker, order)
    assert trade.status == TradeStatus.OPEN
    assert trade.entry_price is None

    result = broker.on_candle("TCS", candle("2026-01-02T09:45:00+05:30", 99, 99.5, 98.5, 99, 500))
    assert result is None  # entry (100) not touched yet


def test_fills_at_entry_level_without_a_gap():
    broker = PaperBroker()
    place(broker, make_order())
    trade = broker.on_candle("TCS", candle("2026-01-02T09:45:00+05:30", 99, 101, 98.5, 100.5, 500))
    assert trade is not None
    assert trade.entry_price == 100.0  # no gap, fills exactly at the entry level
    assert trade.status == TradeStatus.OPEN


def test_gap_fills_at_open_when_candle_opens_through_entry():
    broker = PaperBroker()
    place(broker, make_order(entry=100.0))
    trade = broker.on_candle("TCS", candle("2026-01-02T09:45:00+05:30", 103, 104, 102, 103.5, 500))
    assert trade.entry_price == 103.0  # open (103) is beyond entry (100), fills at open


def test_gap_straight_through_target_expires_instead_of_filling():
    broker = PaperBroker()
    place(broker, make_order(entry=100.0, target=106.0))
    trade = broker.on_candle("TCS", candle("2026-01-02T09:45:00+05:30", 107, 108, 106.5, 107.5, 500))
    assert trade.status == TradeStatus.SKIPPED  # EXPIRED maps to SKIPPED


def test_long_breakeven_then_stop_at_entry_not_original_stop():
    broker = PaperBroker()
    place(broker, make_order(entry=100.0, stop=98.0, breakeven_trigger=102.0))
    broker.on_candle("TCS", candle("2026-01-02T09:45:00+05:30", 99, 101, 98.5, 100.5, 500))  # fills at 100

    # price runs to 103 (through breakeven trigger 102), stop moves to entry (100).
    # Nothing in the Trade record changes yet (no fill, no close), so this
    # candle reports no update - the stop move is internal broker state.
    moved = broker.on_candle("TCS", candle("2026-01-02T09:50:00+05:30", 101, 103, 101, 102.5, 500))
    assert moved is None

    # next candle dips to 99.5 - below the ORIGINAL stop (98) but at/below the breakeven stop (100)
    closed = broker.on_candle("TCS", candle("2026-01-02T09:55:00+05:30", 102, 102.5, 99.5, 100, 500))
    assert closed.status == TradeStatus.CLOSED
    assert closed.net_pnl is not None
    assert closed.exit_price == 100.0  # stopped at breakeven, not the original stop (98)


def test_long_stopped_loss_before_breakeven():
    broker = PaperBroker()
    place(broker, make_order(entry=100.0, stop=98.0, breakeven_trigger=102.0))
    broker.on_candle("TCS", candle("2026-01-02T09:45:00+05:30", 99, 101, 98.5, 100.5, 500))  # fills at 100
    closed = broker.on_candle(
        "TCS", candle("2026-01-02T09:50:00+05:30", 100, 100.5, 97, 97.5, 500)
    )  # drops through stop
    assert closed.status == TradeStatus.CLOSED
    assert closed.exit_price == 98.0
    assert closed.net_pnl < 0


def test_long_target_hit():
    broker = PaperBroker()
    place(broker, make_order(entry=100.0, stop=98.0, target=106.0, breakeven_trigger=102.0))
    broker.on_candle("TCS", candle("2026-01-02T09:45:00+05:30", 99, 101, 98.5, 100.5, 500))  # fills at 100
    closed = broker.on_candle("TCS", candle("2026-01-02T09:50:00+05:30", 101, 107, 100.5, 106.5, 500))
    assert closed.status == TradeStatus.CLOSED
    assert closed.exit_price == 106.0
    assert closed.net_pnl > 0
    assert closed.r_multiple == round((106.0 - 100.0) * 10 / (10 * 2.0), 2)


def test_force_exit_at_session_close():
    broker = PaperBroker()
    place(broker, make_order(entry=100.0, stop=98.0, target=120.0, breakeven_trigger=200.0))
    broker.on_candle("TCS", candle("2026-01-02T09:45:00+05:30", 99, 101, 98.5, 100.5, 500))
    closed = broker.on_candle("TCS", candle("2026-01-02T15:10:00+05:30", 103, 104, 102, 103.5, 500))
    assert closed.status == TradeStatus.CLOSED
    assert closed.exit_price == 103.5


def test_expires_if_never_filled_by_last_entry_time():
    broker = PaperBroker()
    place(broker, make_order(entry=150.0))  # price never gets near 150
    result = broker.on_candle("TCS", candle("2026-01-02T15:10:00+05:30", 100, 101, 99, 100, 500))
    assert result.status == TradeStatus.SKIPPED


def test_short_direction_fills_and_stops_correctly():
    broker = PaperBroker()
    place(broker, make_order(direction=Direction.SHORT, entry=100.0, stop=102.0, target=94.0, breakeven_trigger=98.0))
    filled = broker.on_candle(
        "TCS", candle("2026-01-02T09:45:00+05:30", 101, 101.5, 99, 99.5, 500)
    )  # low 99 <= entry 100
    assert filled.entry_price == 100.0
    closed = broker.on_candle(
        "TCS", candle("2026-01-02T09:50:00+05:30", 99, 102.5, 98.5, 102, 500)
    )  # high breaches stop
    assert closed.status == TradeStatus.CLOSED
    assert closed.exit_price == 102.0
    assert closed.net_pnl < 0


def test_at_most_one_state_change_reported_per_candle_once_closed():
    broker = PaperBroker()
    place(broker, make_order(entry=100.0, stop=98.0, target=106.0, breakeven_trigger=102.0))
    broker.on_candle("TCS", candle("2026-01-02T09:45:00+05:30", 99, 101, 98.5, 100.5, 500))
    broker.on_candle("TCS", candle("2026-01-02T09:50:00+05:30", 101, 107, 100.5, 106.5, 500))  # closes via target
    again = broker.on_candle("TCS", candle("2026-01-02T09:55:00+05:30", 106, 110, 105, 108, 500))
    assert again is None  # plan is terminal, no further updates
