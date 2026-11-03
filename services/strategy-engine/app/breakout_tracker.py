"""Per-symbol opening-range + breakout detection.

Streaming equivalent of the legacy src/backtest/orb_engine.py's
`_find_breakout` / `_entry_and_stop` (same math, ported), restructured
to consume one live candle at a time instead of indexing into a
precomputed array. The entry-fill wait and exit walk
(`_find_entry_fill` / `_walk_to_exit`) stay with execution-engine's
PaperBroker (Phase 5) - this module only decides where the resting
stop-entry/stop-loss order should go.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .params import StrategyParams
from .regime_gate import LONG

# PDF section 5 / orb_engine.py: SL buffer is 0.05%-0.10% of price; 0.075% is the midpoint.
SL_BUFFER_PCT = 0.075


@dataclass
class OpeningRange:
    high: float
    low: float


@dataclass
class Breakout:
    entry_price: float
    stop_price: float
    breakout_time: str
    breakout_volume: int


@dataclass
class SymbolTracker:
    symbol: str
    direction: str
    params: StrategyParams
    opening_range: OpeningRange | None = None
    breakout: Breakout | None = None
    _opening_candles: list[tuple] = field(default_factory=list)

    def on_candle(self, candle: tuple) -> Breakout | None:
        """`candle` = (timestamp, open, high, low, close, volume). Returns
        a Breakout the first time a candle closes beyond the opening
        range; None otherwise (including every call after the first
        breakout - at most one breakout per symbol per day)."""
        if self.breakout is not None:
            return None

        if self.opening_range is None:
            self._opening_candles.append(candle)
            if len(self._opening_candles) < self.params.opening_range_candles:
                return None
            self.opening_range = OpeningRange(
                high=max(c[2] for c in self._opening_candles),
                low=min(c[3] for c in self._opening_candles),
            )
            return None

        close = candle[4]
        broke_out = (
            close > self.opening_range.high if self.direction == LONG else close < self.opening_range.low
        )
        if not broke_out:
            return None

        entry_price, stop_price = _entry_and_stop(self.direction, candle)
        self.breakout = Breakout(
            entry_price=entry_price,
            stop_price=stop_price,
            breakout_time=candle[0],
            breakout_volume=int(candle[5]),
        )
        return self.breakout


def _entry_and_stop(direction: str, breakout_candle: tuple) -> tuple[float, float]:
    _, _open, high, low, _close, _vol = breakout_candle
    if direction == LONG:
        return high, low * (1 - SL_BUFFER_PCT / 100)
    return low, high * (1 + SL_BUFFER_PCT / 100)


def apply_atr_floor(
    direction: str, entry_price: float, stop_price: float, atr_pct: float | None, stop_floor_atr: float
) -> float:
    """Widen the stop to at least `stop_floor_atr` x ATR% away from entry -
    same math as orb_engine.simulate_trade's stop_floor_pct handling."""
    if not atr_pct:
        return stop_price
    floor_pct = stop_floor_atr * atr_pct
    risk = abs(entry_price - stop_price)
    if 100 * risk / entry_price >= floor_pct:
        return stop_price
    floored_risk = entry_price * floor_pct / 100
    return entry_price - floored_risk if direction == LONG else entry_price + floored_risk
