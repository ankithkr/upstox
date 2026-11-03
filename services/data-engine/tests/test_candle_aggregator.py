from app.candle_aggregator import CandleAggregator

FIVE_MIN_MS = 5 * 60 * 1000


def test_ticks_within_same_bucket_update_one_bar():
    agg = CandleAggregator(timeframe_seconds=300)
    bucket_start = 1_700_000_000_000 - (1_700_000_000_000 % FIVE_MIN_MS)

    closed = agg.ingest_tick("NIFTY", price=100.0, qty=5, tick_time_ms=bucket_start)
    assert closed is None
    closed = agg.ingest_tick("NIFTY", price=102.0, qty=3, tick_time_ms=bucket_start + 60_000)
    assert closed is None
    closed = agg.ingest_tick("NIFTY", price=99.0, qty=2, tick_time_ms=bucket_start + 120_000)
    assert closed is None

    bar = agg._open_bars["NIFTY"]
    assert bar.open == 100.0
    assert bar.high == 102.0
    assert bar.low == 99.0
    assert bar.close == 99.0
    assert bar.volume == 10


def test_tick_in_next_bucket_closes_previous_bar():
    agg = CandleAggregator(timeframe_seconds=300)
    bucket_start = 1_700_000_000_000 - (1_700_000_000_000 % FIVE_MIN_MS)

    agg.ingest_tick("NIFTY", price=100.0, qty=5, tick_time_ms=bucket_start)
    agg.ingest_tick("NIFTY", price=105.0, qty=5, tick_time_ms=bucket_start + 100_000)

    closed = agg.ingest_tick("NIFTY", price=110.0, qty=1, tick_time_ms=bucket_start + FIVE_MIN_MS)
    assert closed is not None
    assert closed.close == 105.0
    assert closed.volume == 10

    still_open = agg._open_bars["NIFTY"]
    assert still_open.open == 110.0


def test_flush_returns_and_clears_open_bar():
    agg = CandleAggregator(timeframe_seconds=300)
    agg.ingest_tick("NIFTY", price=100.0, qty=5, tick_time_ms=0)

    bar = agg.flush("NIFTY")
    assert bar is not None
    assert bar.volume == 5
    assert agg.flush("NIFTY") is None


def test_separate_symbols_track_independent_buckets():
    agg = CandleAggregator(timeframe_seconds=300)
    agg.ingest_tick("NIFTY", price=100.0, qty=1, tick_time_ms=0)
    agg.ingest_tick("BANKNIFTY", price=200.0, qty=1, tick_time_ms=0)

    assert agg._open_bars["NIFTY"].open == 100.0
    assert agg._open_bars["BANKNIFTY"].open == 200.0
