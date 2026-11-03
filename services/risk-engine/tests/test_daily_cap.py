from app.daily_cap import DailyCapTracker


def test_accepts_up_to_the_cap():
    tracker = DailyCapTracker(max_trades_per_day=3)
    tracker.reset_if_new_day("2026-02-02")

    for symbol in ["TCS", "INFY", "WIPRO"]:
        can, reason = tracker.can_accept(symbol)
        assert can and reason is None
        tracker.record_accepted(symbol)

    can, reason = tracker.can_accept("HCLTECH")
    assert not can
    assert "3 trades" in reason


def test_rejects_a_second_position_in_the_same_symbol():
    tracker = DailyCapTracker(max_trades_per_day=3)
    tracker.reset_if_new_day("2026-02-02")
    tracker.record_accepted("TCS")

    can, reason = tracker.can_accept("TCS")
    assert not can
    assert "already has a position" in reason


def test_new_day_resets_accepted_symbols():
    tracker = DailyCapTracker(max_trades_per_day=1)
    tracker.reset_if_new_day("2026-02-02")
    tracker.record_accepted("TCS")
    assert not tracker.can_accept("TCS")[0]

    started_new_day = tracker.reset_if_new_day("2026-02-03")
    assert started_new_day
    can, reason = tracker.can_accept("TCS")
    assert can and reason is None


def test_reset_if_new_day_returns_false_for_the_same_day():
    tracker = DailyCapTracker(max_trades_per_day=3)
    assert tracker.reset_if_new_day("2026-02-02") is True
    assert tracker.reset_if_new_day("2026-02-02") is False
