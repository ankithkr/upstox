from app.params import DEFAULT_PARAMS
from app.regime_gate import LONG, SHORT, evaluate_gate, pick_direction


def test_pick_direction_requires_band():
    assert pick_direction(0.1, DEFAULT_PARAMS) is None  # within +/-0.30%
    assert pick_direction(0.31, DEFAULT_PARAMS) == LONG
    assert pick_direction(-0.31, DEFAULT_PARAMS) == SHORT


def test_gate_fails_with_no_direction():
    ok, reasons = evaluate_gate(None, vix=12.0, nifty_trend_pct=1.0, params=DEFAULT_PARAMS)
    assert not ok
    assert "no side" in reasons[0]


def test_gate_fails_on_high_vix():
    ok, reasons = evaluate_gate(LONG, vix=16.0, nifty_trend_pct=1.0, params=DEFAULT_PARAMS)
    assert not ok
    assert any("VIX" in r for r in reasons)


def test_gate_fails_without_matching_trend():
    # LONG needs an uptrend (trend_pct > 0); a downtrend should fail it.
    ok, reasons = evaluate_gate(LONG, vix=12.0, nifty_trend_pct=-1.0, params=DEFAULT_PARAMS)
    assert not ok
    assert any("downtrend" not in r and "uptrend" in r for r in reasons)


def test_gate_passes_when_everything_lines_up():
    ok, reasons = evaluate_gate(LONG, vix=12.0, nifty_trend_pct=1.5, params=DEFAULT_PARAMS)
    assert ok
    assert reasons == []


def test_short_gate_needs_downtrend():
    ok, _ = evaluate_gate(SHORT, vix=12.0, nifty_trend_pct=-1.5, params=DEFAULT_PARAMS)
    assert ok
    ok, _ = evaluate_gate(SHORT, vix=12.0, nifty_trend_pct=1.5, params=DEFAULT_PARAMS)
    assert not ok
