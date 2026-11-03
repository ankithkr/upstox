"""strategy-engine: the ported v2 ORB rules.

Loads the 20-day reference history once (and once per new trading day),
subscribes to the `candles` Redis channel from data-engine, runs every
candle through the day's DayPlan (regime gate -> sector/stock filters ->
per-symbol breakout detection), and publishes a Signal to the `signals`
channel the moment a qualifying stock's breakout clears the volume
filter too.
"""

from __future__ import annotations

import asyncio
import logging

from shared.messaging import CHANNEL_CANDLES, CHANNEL_SIGNALS, get_redis, publish, subscribe
from shared.models import Candle, Direction, Signal
from shared.universe import INDEX_CONSTITUENTS

from .breakout_tracker import apply_atr_floor
from .day_plan import DayPlan
from .history import load_history
from .instruments import build_equity_symbol_index, load_instrument_master
from .live_reference import latest_atr_pct, live_slot_volume_ratio
from .params import DEFAULT_PARAMS
from .regime_gate import LONG

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("strategy-engine")


def _to_tuple(candle: Candle) -> tuple:
    ts = candle.open_time.isoformat()
    return (ts, candle.open, candle.high, candle.low, candle.close, candle.volume)


def _sector_for(symbol: str, selected_sectors: list[str]) -> str:
    for name in selected_sectors:
        if symbol in INDEX_CONSTITUENTS.get(name, []):
            return name
    return "unknown"


async def _handle_breakout(day_plan: DayPlan, history, params, symbol: str, instrument_key: str, breakout) -> Signal:
    atr_pct = latest_atr_pct(history.stock_daily[symbol])
    stop_price = apply_atr_floor(
        day_plan.direction, breakout.entry_price, breakout.stop_price, atr_pct, params.stop_floor_atr
    )
    risk = abs(breakout.entry_price - stop_price)
    sign = 1 if day_plan.direction == LONG else -1
    target_price = breakout.entry_price + sign * params.target_rrr * risk
    breakeven_trigger = (
        breakout.entry_price + sign * params.breakeven_rrr * risk if params.breakeven_rrr is not None else None
    )
    return Signal(
        id=f"{symbol}-{breakout.breakout_time}",
        symbol=symbol,
        direction=Direction.LONG if day_plan.direction == LONG else Direction.SHORT,
        sector=_sector_for(symbol, day_plan.selected_sectors),
        detected_at=breakout.breakout_time,
        breakout_price=breakout.entry_price,
        stop_price=stop_price,
        breakeven_trigger=breakeven_trigger,
        target_price=target_price,
        filters_passed=["regime_gate", "sector", "stock", "breakout_volume"],
    )


async def main() -> None:
    log.info("strategy-engine starting: loading reference history...")
    symbol_keys = build_equity_symbol_index(load_instrument_master())
    history = load_history()
    log.info("history loaded: %d days, %d missing symbols", len(history.days), len(history.missing_symbols))

    params = DEFAULT_PARAMS
    redis = get_redis()

    day_plan: DayPlan | None = None
    current_date: str | None = None

    async for raw in subscribe(redis, CHANNEL_CANDLES):
        candle = Candle.model_validate_json(raw)
        candle_tuple = _to_tuple(candle)
        date = candle_tuple[0][:10]

        if date != current_date:
            log.info("new trading day %s, resetting day plan", date)
            current_date = date
            day_plan = DayPlan(history, symbol_keys, params)

        breakout = day_plan.feed_candle(candle.symbol, candle_tuple)
        if breakout is None:
            continue

        symbol = day_plan.key_to_symbol.get(candle.symbol)
        if symbol is None:
            continue

        volume_ratio = live_slot_volume_ratio(
            history.stock_volume[symbol], breakout.breakout_time, breakout.breakout_volume
        )
        if volume_ratio is None or volume_ratio < params.min_breakout_volume_ratio:
            log.info(
                "%s breakout skipped: volume ratio %s < %.1f",
                symbol, volume_ratio, params.min_breakout_volume_ratio,
            )
            continue

        signal = await _handle_breakout(day_plan, history, params, symbol, candle.symbol, breakout)
        await publish(redis, CHANNEL_SIGNALS, signal)
        log.info(
            "signal emitted: %s %s entry=%.2f stop=%.2f target=%.2f",
            symbol, day_plan.direction, signal.breakout_price, signal.stop_price, signal.target_price,
        )


if __name__ == "__main__":
    asyncio.run(main())
