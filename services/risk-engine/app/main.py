"""risk-engine: position sizing, capital checks, daily trade cap.

Subscribes to the `signals` Redis channel from strategy-engine. For
each signal: enforce the daily cap (one position per symbol, at most
`MAX_TRADES_PER_DAY` a day), size it (1% risk, no leverage, qty capped
by free cash), and publish an OrderIntent to the `orders` channel for
execution-engine. A signal that fails either check is skipped and
logged, never queued - there is no retry.
"""

from __future__ import annotations

import asyncio
import logging
import os

from shared.messaging import CHANNEL_ORDERS, CHANNEL_SIGNALS, get_redis, publish, subscribe
from shared.models import OrderIntent, Signal

from .daily_cap import DailyCapTracker
from .equity import latest_equity
from .sizing import size_order

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("risk-engine")

RISK_PER_TRADE_PCT = float(os.environ.get("RISK_PER_TRADE_PCT", "1.0"))
LEVERAGE = float(os.environ.get("LEVERAGE", "1.0"))
PAPER_CAPITAL = float(os.environ.get("PAPER_CAPITAL", "100000"))
MAX_TRADES_PER_DAY = int(os.environ.get("MAX_TRADES_PER_DAY", "3"))


async def main() -> None:
    redis = get_redis()
    cap_tracker = DailyCapTracker(MAX_TRADES_PER_DAY)
    equity = PAPER_CAPITAL
    cash = PAPER_CAPITAL

    log.info(
        "risk-engine starting: risk_per_trade=%.1f%% leverage=%.1fx max_trades_per_day=%d",
        RISK_PER_TRADE_PCT, LEVERAGE, MAX_TRADES_PER_DAY,
    )

    async for raw in subscribe(redis, CHANNEL_SIGNALS):
        signal = Signal.model_validate_json(raw)
        date = signal.detected_at.date().isoformat()

        if cap_tracker.reset_if_new_day(date):
            equity = latest_equity(default=PAPER_CAPITAL)
            cash = equity
            log.info("new trading day %s, starting equity=%.2f", date, equity)

        can_accept, reason = cap_tracker.can_accept(signal.symbol)
        if not can_accept:
            log.info("signal skipped for %s: %s", signal.symbol, reason)
            continue

        result = size_order(signal, equity=equity, cash=cash, risk_pct=RISK_PER_TRADE_PCT, leverage=LEVERAGE)
        if result.skipped:
            log.info("signal skipped for %s: %s", signal.symbol, result.skip_reason)
            continue

        order = OrderIntent(
            id=f"{signal.id}-order",
            signal_id=signal.id,
            symbol=signal.symbol,
            direction=signal.direction,
            qty=result.qty,
            entry_price=signal.breakout_price,
            stop_price=signal.stop_price,
            target_price=signal.target_price,
            risk_amount=result.risk_amount,
        )
        cash -= result.qty * signal.breakout_price
        cap_tracker.record_accepted(signal.symbol)

        await publish(redis, CHANNEL_ORDERS, order)
        log.info(
            "order sized: %s qty=%d risk=%.2f cash_remaining=%.2f",
            signal.symbol, result.qty, result.risk_amount, cash,
        )


if __name__ == "__main__":
    asyncio.run(main())
