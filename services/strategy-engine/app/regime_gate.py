"""The market regime gate - ported verbatim from the legacy
src/backtest/snapshots.py's `evaluate_gate` ("the single biggest
profitability lever" per params.py). Decides, once per trading day,
whether today is tradeable at all and which side."""

from __future__ import annotations

from .params import StrategyParams

LONG = "LONG"
SHORT = "SHORT"

BULLISH, BEARISH, NEUTRAL = "BULLISH", "BEARISH", "NEUTRAL"
NO_TRADE = "NO_TRADE"


def pick_direction(nifty_930_change_pct: float, params: StrategyParams) -> str | None:
    if abs(nifty_930_change_pct) > params.nifty_band_pct:
        return LONG if nifty_930_change_pct > 0 else SHORT
    return None


def evaluate_gate(
    direction: str | None, vix: float | None, nifty_trend_pct: float | None, params: StrategyParams
) -> tuple[bool, list[str]]:
    """Is the market regime tradeable? Returns (ok, reasons it is not)."""
    if direction is None:
        return False, [f"NIFTY 09:30 move within ±{params.nifty_band_pct}% - no side"]
    reasons = []
    if vix is None:
        reasons.append("no India VIX reading")
    elif vix >= params.max_vix:
        reasons.append(f"VIX {vix:.1f} ≥ {params.max_vix:g}")
    sign = 1 if direction == LONG else -1
    if nifty_trend_pct is None:
        reasons.append("no NIFTY 20-day trend")
    elif sign * nifty_trend_pct <= params.min_nifty_trend_pct:
        want = "uptrend" if direction == LONG else "downtrend"
        reasons.append(f"NIFTY 20-day trend {nifty_trend_pct:+.1f}% - no {want} to trade with")
    return not reasons, reasons
