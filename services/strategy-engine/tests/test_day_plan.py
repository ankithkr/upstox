"""End-to-end test of the day plan: regime gate -> sector selection ->
stock qualification -> breakout, using one real sector/stock pair from
the ported universe (NIFTY IT / INFY) so INDEX_CONSTITUENTS lookups are
real, but a synthetic History so the test doesn't depend on the local
candle cache being populated."""

from app.day_plan import DayPlan
from app.features import DailyIndex, VolumeProfile
from app.history import History
from app.params import StrategyParams
from app.regime_gate import LONG
from shared.universe import NIFTY_50_INSTRUMENT_KEY, SECTOR_INDEX_INSTRUMENT_KEYS, V2_SECTORS

PARAMS = StrategyParams()  # defaults: opening_range_candles=6, min_opening_volume_ratio=1.0, min_breakout_volume_ratio=1.5
NIFTY_IT_KEY = SECTOR_INDEX_INSTRUMENT_KEYS["NIFTY IT"]
INFY_KEY = "NSE_EQ|TEST_INFY"


def _ascending_daily(n: int, start: float, step: float) -> list[tuple]:
    return [
        (f"2026-01-{i + 1:02d}T00:00:00+05:30", start + i * step, start + i * step + 1, start + i * step - 1, start + i * step, 1000)
        for i in range(n)
    ]


def _flat_daily(n: int, close: float) -> list[tuple]:
    return [(f"2026-01-{i + 1:02d}T00:00:00+05:30", close, close + 1, close - 1, close, 1000) for i in range(n)]


def _infy_history_days(n: int) -> dict[str, list[tuple]]:
    by_day = {}
    for i in range(n):
        day = f"2026-01-{i + 1:02d}"
        slots = ["09:15", "09:20", "09:25", "09:30", "09:35", "09:40", "09:45"]
        by_day[day] = [(f"{day}T{slot}:00+05:30", 1500, 1501, 1499, 1500, 100) for slot in slots]
    return by_day


def build_history() -> History:
    sector_daily = {name: DailyIndex(_flat_daily(5, 100.0)) for name in V2_SECTORS}
    infy_by_day = _infy_history_days(16)
    return History(
        nifty_15m={},
        # ascending series ending at close=100.0 -> latest_close()==100.0 and trend_pct > 0
        nifty_daily=DailyIndex(_ascending_daily(25, 88.0, 0.5)),
        vix_daily=DailyIndex(_flat_daily(1, 12.0)),  # below max_vix=14
        sector_15m={},
        sector_daily=sector_daily,
        stock_5m={},
        stock_daily={"INFY": DailyIndex(_flat_daily(16, 1500.0))},
        stock_volume={"INFY": VolumeProfile(infy_by_day)},
        missing_symbols=[],
    )


def candle(ts, o, h, l, c, v):
    return (ts, o, h, l, c, v)


def test_full_pipeline_gate_sector_stock_breakout():
    history = build_history()
    symbol_keys = {"INFY": INFY_KEY}
    plan = DayPlan(history, symbol_keys, PARAMS)

    # NIFTY: 3 candles, 3rd candle's close gives a +0.5% move (> 0.30% band) -> LONG
    for c in [
        candle("2026-02-02T09:15:00+05:30", 100, 101, 99, 100.2, 1000),
        candle("2026-02-02T09:20:00+05:30", 100.2, 101, 99, 100.3, 1000),
        candle("2026-02-02T09:25:00+05:30", 100.3, 101, 99, 100.5, 1000),  # +0.5% vs prev close 100
    ]:
        assert plan.feed_candle(NIFTY_50_INSTRUMENT_KEY, c) is None

    # All 16 V2_SECTORS need 3 candles before the plan resolves. Make
    # NIFTY IT strongly bullish (+2%, prev close 100); everything else flat/no-trade.
    for name in V2_SECTORS:
        key = SECTOR_INDEX_INSTRUMENT_KEYS[name]
        third_close = 102.0 if name == "NIFTY IT" else 100.1
        for i, c in enumerate([
            candle(f"t{name}1", 100, 101, 99, 100, 1000),
            candle(f"t{name}2", 100, 101, 99, 100, 1000),
            candle(f"t{name}3", 100, 101, 99, third_close, 1000),
        ]):
            result = plan.feed_candle(key, c)
            if name != "NIFTY IT":
                assert result is None

    # INFY's own 3 candles complete the snapshot: +1.5% move (prev close 1500),
    # opening volume 450 vs the 300 baseline (ratio 1.5, >= min 1.0).
    assert plan.feed_candle(INFY_KEY, candle("i1", 1500, 1525, 1515, 1522.5, 150)) is None
    assert plan.feed_candle(INFY_KEY, candle("i2", 1522.5, 1525, 1515, 1522.5, 150)) is None
    breakout = plan.feed_candle(INFY_KEY, candle("i3", 1522.5, 1525, 1515, 1522.5, 150))

    assert plan.resolved
    assert plan.direction == LONG
    assert plan.gate_ok
    assert plan.selected_sectors == ["NIFTY IT"]
    assert "INFY" in plan.trackers
    assert breakout is None  # third candle only completes the 09:30 snapshot, not the opening range

    # Candles 4-6 complete the 6-candle opening range (09:15-09:45), no breakout yet.
    for c in [
        candle("i4", 1522.5, 1525, 1520, 1522.5, 100),
        candle("i5", 1522.5, 1525, 1520, 1522.5, 100),
        candle("i6", 1522.5, 1525, 1520, 1522.5, 100),
    ]:
        assert plan.feed_candle(INFY_KEY, c) is None

    tracker = plan.trackers["INFY"]
    assert tracker.opening_range.high == 1525
    assert tracker.opening_range.low == 1515

    # 7th candle closes above the opening range high (1525) with 2x the
    # historical "09:45"-slot volume baseline (100) -> breakout fires.
    breakout = plan.feed_candle(INFY_KEY, candle("2026-02-02T09:45:00+05:30", 1525, 1532, 1524, 1530, 200))

    assert breakout is not None
    assert breakout.entry_price == 1532  # breakout candle's high
    assert breakout.breakout_volume == 200


def test_gate_closed_day_creates_no_trackers():
    history = build_history()
    symbol_keys = {"INFY": INFY_KEY}
    plan = DayPlan(history, symbol_keys, PARAMS)

    # NIFTY move within the +/-0.30% band -> no direction -> gate fails -> day closed.
    for c in [
        candle("t1", 100, 101, 99, 100.0, 1000),
        candle("t2", 100, 101, 99, 100.0, 1000),
        candle("t3", 100, 101, 99, 100.05, 1000),
    ]:
        plan.feed_candle(NIFTY_50_INSTRUMENT_KEY, c)

    for name in V2_SECTORS:
        key = SECTOR_INDEX_INSTRUMENT_KEYS[name]
        for c in [
            candle("s1", 100, 101, 99, 100, 1000),
            candle("s2", 100, 101, 99, 100, 1000),
            candle("s3", 100, 101, 99, 100, 1000),
        ]:
            plan.feed_candle(key, c)

    plan.feed_candle(INFY_KEY, candle("i1", 1500, 1501, 1499, 1500, 150))
    plan.feed_candle(INFY_KEY, candle("i2", 1500, 1501, 1499, 1500, 150))
    plan.feed_candle(INFY_KEY, candle("i3", 1500, 1501, 1499, 1500, 150))

    assert plan.resolved
    assert plan.direction is None
    assert not plan.gate_ok
    assert plan.trackers == {}
