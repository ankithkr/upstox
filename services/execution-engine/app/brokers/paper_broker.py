"""PaperBroker: simulates fills against the live candle feed.

The fill/exit mechanics (resting stop-entry order, gap fills, breakeven
stop move, force exit) are ported from the legacy src/paper/engine.py's
`walk()` - the part of that file that is pure order mechanics, not
tied to the old v1 strategy rules (which chose entry/stop/target/
breakeven differently; those now come from the OrderIntent itself,
already computed by the v2 strategy-engine + risk-engine).

Unlike the legacy engine (which replays a whole day's closed candles
per tick), this advances one candle at a time as data-engine's feed
closes each one, since this runs live.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from shared.broker import Broker
from shared.models import Direction, OrderIntent, Position, Trade, TradeStatus

from ..charges import round_trip_charges

LONG = "LONG"
SHORT = "SHORT"

TARGET_HIT = "TARGET_HIT"
STOPPED_LOSS = "STOPPED_LOSS"
STOPPED_BREAKEVEN = "STOPPED_BREAKEVEN"
EOD_EXIT = "EOD_EXIT"
EXPIRED = "EXPIRED"

# Candle-start times (HH:MM). Ported from src/paper/config.py defaults.
FORCE_EXIT_CANDLE_START = os.environ.get("FORCE_EXIT_CANDLE_START", "15:10")
LAST_ENTRY_CANDLE_START = os.environ.get("LAST_ENTRY_CANDLE_START", "15:10")
SLIPPAGE_PCT = float(os.environ.get("PAPER_SLIPPAGE_PCT", "0.0"))

PENDING, OPEN, CLOSED = "PENDING", "OPEN", "CLOSED"


def _hhmm(ts: str) -> str:
    return ts[11:16]


def _offset(direction: str, price: float, amount: float) -> float:
    return price + amount if direction == LONG else price - amount


@dataclass
class _PlanState:
    order: OrderIntent
    state: str = PENDING
    entry_time: datetime | None = None
    entry_price: float | None = None
    current_stop: float | None = None
    at_breakeven: bool = False
    outcome: str | None = None
    exit_time: datetime | None = None
    exit_price: float | None = None
    last_price: float | None = None
    gross_pnl: float | None = None
    charges: float | None = None
    net_pnl: float | None = None
    r_multiple: float | None = None
    _entry_candle_time: datetime | None = field(default=None, repr=False)

    @property
    def direction(self) -> str:
        return LONG if self.order.direction == Direction.LONG else SHORT

    def is_terminal(self) -> bool:
        return self.state == CLOSED or self.outcome == EXPIRED

    def advance(self, candle: tuple) -> bool:
        """candle = (timestamp, open, high, low, close, volume). Returns
        True if this call changed the plan's state (fill or close)."""
        ts, o, h, l, c, _v = candle
        candle_time = datetime.fromisoformat(ts)
        start = _hhmm(ts)
        d = self.direction

        if self.state == PENDING:
            if start >= LAST_ENTRY_CANDLE_START:
                self.outcome = EXPIRED
                return True
            triggered = h >= self.order.entry_price if d == LONG else l <= self.order.entry_price
            if not triggered:
                return False

            fill = max(self.order.entry_price, o) if d == LONG else min(self.order.entry_price, o)
            past_target = fill >= self.order.target_price if d == LONG else fill <= self.order.target_price
            if past_target:  # gapped straight through the target - not a tradeable fill
                self.outcome = EXPIRED
                return True

            slip = SLIPPAGE_PCT / 100
            self.entry_price = fill * (1 + slip) if d == LONG else fill * (1 - slip)
            self.entry_time = candle_time
            self._entry_candle_time = candle_time
            self.current_stop = self.order.stop_price
            self.state = OPEN
            # fall through: the entry candle itself can already hit stop/target

        if self.state == OPEN:
            is_entry_candle = candle_time == self._entry_candle_time
            moved_be_now = False
            if not self.at_breakeven and self.order.breakeven_trigger is not None:
                reached = h >= self.order.breakeven_trigger if d == LONG else l <= self.order.breakeven_trigger
                if reached:
                    self.current_stop = self.entry_price
                    self.at_breakeven = moved_be_now = True

            stopped = l <= self.current_stop if d == LONG else h >= self.current_stop
            hit_target = h >= self.order.target_price if d == LONG else l <= self.order.target_price
            gap_ok = not is_entry_candle

            slip = SLIPPAGE_PCT / 100
            if stopped:
                px = self.current_stop
                if gap_ok and not moved_be_now:
                    px = min(px, o) if d == LONG else max(px, o)
                px = px * (1 - slip) if d == LONG else px * (1 + slip)
                self._close(STOPPED_BREAKEVEN if self.at_breakeven else STOPPED_LOSS, candle_time, px)
                return True
            if hit_target:
                px = self.order.target_price
                if gap_ok:
                    px = max(px, o) if d == LONG else min(px, o)
                self._close(TARGET_HIT, candle_time, px)
                return True
            if start >= FORCE_EXIT_CANDLE_START:
                px = c * (1 - slip) if d == LONG else c * (1 + slip)
                self._close(EOD_EXIT, candle_time + timedelta(minutes=5), px)
                return True
            self.last_price = c
            return is_entry_candle  # filling is itself a state change worth reporting

        return False

    def _close(self, outcome: str, exit_time: datetime, price: float) -> None:
        self.state, self.outcome = CLOSED, outcome
        self.exit_time, self.exit_price = exit_time, price
        qty = self.order.qty
        d = self.direction
        self.gross_pnl = round((price - self.entry_price) * qty if d == LONG else (self.entry_price - price) * qty, 2)
        self.charges = round_trip_charges(d, qty, self.entry_price, price)
        self.net_pnl = round(self.gross_pnl - self.charges, 2)
        risk_per_share = abs(self.order.entry_price - self.order.stop_price)
        self.r_multiple = round(self.gross_pnl / (qty * risk_per_share), 2) if risk_per_share else None

    def to_trade(self) -> Trade:
        status = TradeStatus.CLOSED if self.state == CLOSED else (
            TradeStatus.SKIPPED if self.outcome == EXPIRED else TradeStatus.OPEN
        )
        return Trade(
            id=f"{self.order.id}-trade",
            order_id=self.order.id,
            symbol=self.order.symbol,
            direction=self.order.direction,
            status=status,
            qty=self.order.qty,
            entry_price=self.entry_price,
            entry_time=self.entry_time,
            exit_price=self.exit_price,
            exit_time=self.exit_time,
            gross_pnl=self.gross_pnl,
            charges=self.charges,
            net_pnl=self.net_pnl,
            r_multiple=self.r_multiple,
        )


class PaperBroker(Broker):
    def __init__(self) -> None:
        self._plans: dict[str, _PlanState] = {}

    async def place_order(self, order: OrderIntent) -> Trade:
        plan = _PlanState(order=order)
        self._plans[order.id] = plan
        return plan.to_trade()

    def on_candle(self, symbol: str, candle: tuple) -> Trade | None:
        """Advances every non-terminal plan for `symbol` by one closed
        candle. Risk-engine allows at most one open position per symbol
        per day, so at most one plan is live at a time in practice."""
        for plan in self._plans.values():
            if plan.order.symbol != symbol or plan.is_terminal():
                continue
            if plan.advance(candle):
                return plan.to_trade()
        return None

    async def get_trade(self, order_id: str) -> Trade | None:
        plan = self._plans.get(order_id)
        return plan.to_trade() if plan else None

    async def cancel_order(self, order_id: str) -> None:
        self._plans.pop(order_id, None)

    async def get_positions(self) -> list[Position]:
        positions = []
        for plan in self._plans.values():
            if plan.state != OPEN:
                continue
            positions.append(
                Position(
                    symbol=plan.order.symbol,
                    direction=plan.order.direction,
                    qty=plan.order.qty,
                    avg_entry_price=plan.entry_price,
                )
            )
        return positions
