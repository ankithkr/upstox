"""PaperBroker: simulates fills against the live candle feed.

Implements shared.broker.Broker. Phase 5 fills this in using the cost
model ported from the legacy src/backtest/costs.py (brokerage, STT,
exchange, GST, stamp, slippage) and the same gap-fill-at-open logic the
legacy paper_trade.py used for resting stop-entry / SL / target orders.
"""

from __future__ import annotations

from shared.broker import Broker
from shared.models import OrderIntent, Position, Trade


class PaperBroker(Broker):
    async def place_order(self, order: OrderIntent) -> Trade:
        raise NotImplementedError("Phase 5: simulate the fill against the live candle feed")

    async def get_trade(self, order_id: str) -> Trade | None:
        raise NotImplementedError

    async def cancel_order(self, order_id: str) -> None:
        raise NotImplementedError

    async def get_positions(self) -> list[Position]:
        raise NotImplementedError
