"""execution-engine: owns the Broker interface, runs PaperBroker today.

Two concurrent consumers share one PaperBroker instance:
  - `orders` (from risk-engine): place the resting order.
  - `candles` (from data-engine): advance every resting/open order one
    closed candle at a time; a closed trade updates the Ledger and
    writes an equity snapshot.

`candles` is keyed by Upstox instrument key (data-engine's own view of
the world); orders/trades are keyed by trading symbol (risk-engine's
and strategy-engine's view) - resolved here via the local instrument
master, the same mapping strategy-engine uses in the other direction.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

from shared.messaging import CHANNEL_CANDLES, CHANNEL_ORDERS, get_redis, subscribe
from shared.models import Candle, OrderIntent, TradeStatus

from . import persistence
from .brokers.paper_broker import PaperBroker
from .instruments import build_key_to_symbol_index, load_instrument_master
from .ledger import Ledger

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("execution-engine")

PAPER_CAPITAL = float(os.environ.get("PAPER_CAPITAL", "100000"))


def _to_tuple(candle: Candle) -> tuple:
    return (candle.open_time.isoformat(), candle.open, candle.high, candle.low, candle.close, candle.volume)


async def consume_orders(broker: PaperBroker, redis) -> None:
    async for raw in subscribe(redis, CHANNEL_ORDERS):
        order = OrderIntent.model_validate_json(raw)
        trade = await broker.place_order(order)
        persistence.upsert_order(order)
        persistence.upsert_trade(trade)
        log.info(
            "order received: %s qty=%d entry=%.2f stop=%.2f target=%.2f",
            order.symbol, order.qty, order.entry_price, order.stop_price, order.target_price,
        )


async def consume_candles(broker: PaperBroker, ledger: Ledger, redis, key_to_symbol: dict[str, str]) -> None:
    async for raw in subscribe(redis, CHANNEL_CANDLES):
        candle = Candle.model_validate_json(raw)
        symbol = key_to_symbol.get(candle.symbol)
        if symbol is None:
            continue  # an index/sector candle, or a stock with no open order

        trade = broker.on_candle(symbol, _to_tuple(candle))
        if trade is None:
            continue

        persistence.upsert_trade(trade)
        if trade.status == TradeStatus.CLOSED and trade.net_pnl is not None:
            ledger.apply_closed_trade(trade.net_pnl)
            persistence.write_equity_snapshot(datetime.now(timezone.utc), ledger.equity, ledger.equity)
            log.info("trade closed: %s net_pnl=%.2f equity=%.2f", trade.symbol, trade.net_pnl, ledger.equity)
        else:
            log.info("trade update: %s status=%s entry=%s", trade.symbol, trade.status, trade.entry_price)


async def main() -> None:
    redis = get_redis()
    broker = PaperBroker()
    ledger = Ledger(starting_capital=PAPER_CAPITAL)
    key_to_symbol = build_key_to_symbol_index(load_instrument_master())

    log.info("execution-engine starting: paper capital=%.2f", PAPER_CAPITAL)
    await asyncio.gather(
        consume_orders(broker, redis),
        consume_candles(broker, ledger, redis, key_to_symbol),
    )


if __name__ == "__main__":
    asyncio.run(main())
