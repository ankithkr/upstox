"""Position sizing: 1% risk, no leverage.

Ported from the legacy src/paper/engine.py's `build_trades` sizing math
(qty = min(risk-budget / risk-per-share, free-cash / entry price)), the
one part of that file that isn't v1-strategy-specific - adapted here to
size one signal at a time against the day's running cash, instead of a
whole day's fills in a batch.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from shared.models import Signal


@dataclass(frozen=True)
class SizingResult:
    qty: int
    risk_amount: float
    skipped: bool
    skip_reason: str | None = None


def size_order(signal: Signal, equity: float, cash: float, risk_pct: float, leverage: float) -> SizingResult:
    risk_per_share = abs(signal.breakout_price - signal.stop_price)
    if risk_per_share <= 0:
        return SizingResult(0, 0.0, True, "zero risk per share")

    risk_budget = equity * risk_pct / 100
    qty_by_risk = math.floor(risk_budget / risk_per_share)

    buying_power = max(cash, 0) * leverage
    qty_by_cash = math.floor(buying_power / signal.breakout_price) if signal.breakout_price else 0

    qty = min(qty_by_risk, qty_by_cash)
    if qty < 1:
        reason = (
            "one share risks more than the per-trade risk budget"
            if qty_by_risk < 1
            else "not enough free cash for one share"
        )
        return SizingResult(0, 0.0, True, reason)

    return SizingResult(qty, round(qty * risk_per_share, 2), False)
