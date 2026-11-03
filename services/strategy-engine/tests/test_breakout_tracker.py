from app.breakout_tracker import SymbolTracker, apply_atr_floor
from app.params import StrategyParams
from app.regime_gate import LONG, SHORT

PARAMS = StrategyParams(opening_range_candles=3)


def candle(ts, o, h, l, c, v):
    return (ts, o, h, l, c, v)


def test_no_breakout_during_opening_range_candles():
    tracker = SymbolTracker("TCS", LONG, PARAMS)
    assert tracker.on_candle(candle("t1", 100, 102, 99, 101, 1000)) is None
    assert tracker.on_candle(candle("t2", 101, 103, 100, 102, 1000)) is None
    # third candle completes the opening range; range itself never breaks out
    assert tracker.on_candle(candle("t3", 102, 104, 101, 103, 1000)) is None
    assert tracker.opening_range.high == 104
    assert tracker.opening_range.low == 99


def test_long_breakout_fires_on_close_beyond_range_high():
    tracker = SymbolTracker("TCS", LONG, PARAMS)
    for c in [candle("t1", 100, 102, 99, 101, 1000), candle("t2", 101, 103, 100, 102, 1000), candle("t3", 102, 104, 101, 103, 1000)]:
        tracker.on_candle(c)

    no_breakout = tracker.on_candle(candle("t4", 103, 104, 102, 103.5, 500))  # close 103.5 < range high 104
    assert no_breakout is None

    breakout = tracker.on_candle(candle("t5", 103.5, 106, 103, 105, 2000))  # close 105 > 104
    assert breakout is not None
    assert breakout.entry_price == 106  # breakout candle's high
    assert breakout.breakout_volume == 2000
    assert tracker.breakout is breakout


def test_short_breakout_fires_on_close_beyond_range_low():
    tracker = SymbolTracker("TCS", SHORT, PARAMS)
    for c in [candle("t1", 100, 102, 99, 101, 1000), candle("t2", 101, 103, 100, 98, 1000), candle("t3", 98, 99, 95, 97, 1000)]:
        tracker.on_candle(c)
    assert tracker.opening_range.low == 95

    breakout = tracker.on_candle(candle("t4", 97, 98, 90, 92, 1500))  # close 92 < range low 95
    assert breakout is not None
    assert breakout.entry_price == 90  # breakout candle's low


def test_at_most_one_breakout_per_symbol():
    tracker = SymbolTracker("TCS", LONG, PARAMS)
    for c in [candle("t1", 100, 102, 99, 101, 1000), candle("t2", 101, 103, 100, 102, 1000), candle("t3", 102, 104, 101, 103, 1000)]:
        tracker.on_candle(c)
    first = tracker.on_candle(candle("t4", 104, 110, 104, 108, 1000))
    assert first is not None
    second = tracker.on_candle(candle("t5", 108, 120, 107, 115, 1000))
    assert second is None


def test_apply_atr_floor_widens_a_too_tight_stop():
    # entry=100, stop=99.9 => risk 0.1% of entry, floor wants 0.4*2.0=0.8%
    stop = apply_atr_floor(LONG, entry_price=100.0, stop_price=99.9, atr_pct=2.0, stop_floor_atr=0.4)
    assert stop == 100.0 - 100.0 * 0.8 / 100


def test_apply_atr_floor_leaves_an_already_wide_stop_alone():
    stop = apply_atr_floor(LONG, entry_price=100.0, stop_price=95.0, atr_pct=2.0, stop_floor_atr=0.4)
    assert stop == 95.0


def test_apply_atr_floor_noop_when_atr_unknown():
    stop = apply_atr_floor(LONG, entry_price=100.0, stop_price=99.9, atr_pct=None, stop_floor_atr=0.4)
    assert stop == 99.9
