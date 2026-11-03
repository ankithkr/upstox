"""data-engine: Upstox WebSocket feed -> 5-min candle aggregation -> Redis publish.

During market hours, authorizes and holds an Upstox Market Data Feed V3
connection for the configured instrument keys, aggregates LTP ticks into
closed candles, and publishes each one to the `candles` Redis channel for
strategy-engine. Outside market hours it idles and re-checks every minute.
"""

from __future__ import annotations

import asyncio
import logging
import os

import websockets

from shared.messaging import CHANNEL_CANDLES, get_redis, publish

from .auth import load_access_token
from .candle_aggregator import CandleAggregator
from .feed_client import get_authorized_ws_url, stream_feed
from .market_hours import is_market_open

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("data-engine")

CANDLE_TIMEFRAME_SECONDS = int(os.environ.get("CANDLE_TIMEFRAME_SECONDS", "300"))
FEED_MODE = os.environ.get("UPSTOX_FEED_MODE", "ltpc")


def _instrument_keys() -> list[str]:
    raw = os.environ.get("INSTRUMENT_KEYS", "NSE_INDEX|Nifty 50")
    return [key.strip() for key in raw.split(",") if key.strip()]


async def run_session(instrument_keys: list[str]) -> None:
    redis = get_redis()
    aggregator = CandleAggregator(timeframe_seconds=CANDLE_TIMEFRAME_SECONDS)

    access_token = load_access_token()
    ws_url = await get_authorized_ws_url(access_token)
    log.info("authorized websocket url obtained")

    async for feed_response in stream_feed(ws_url, instrument_keys, mode=FEED_MODE):
        if feed_response.type != feed_response.Type.live_feed:
            continue
        for instrument_key, feed in feed_response.feeds.items():
            case = feed.WhichOneof("FeedUnion")
            if case != "ltpc":
                continue
            closed = aggregator.ingest_tick(
                symbol=instrument_key,
                price=feed.ltpc.ltp,
                qty=feed.ltpc.ltq,
                tick_time_ms=feed.ltpc.ltt,
            )
            if closed is not None:
                await publish(redis, CHANNEL_CANDLES, closed)
                log.info("closed candle %s %s O=%.2f H=%.2f L=%.2f C=%.2f V=%d",
                          closed.symbol, closed.open_time, closed.open, closed.high,
                          closed.low, closed.close, closed.volume)

        if not is_market_open():
            log.info("market hours over, flushing open bars and ending session")
            for instrument_key in instrument_keys:
                bar = aggregator.flush(instrument_key)
                if bar is not None:
                    await publish(redis, CHANNEL_CANDLES, bar)
            return


async def main() -> None:
    instrument_keys = _instrument_keys()
    log.info("data-engine starting, tracking %d instrument key(s)", len(instrument_keys))

    while True:
        if not is_market_open():
            await asyncio.sleep(60)
            continue

        try:
            await run_session(instrument_keys)
        except (websockets.ConnectionClosed, OSError) as exc:
            log.warning("feed connection dropped (%s), reconnecting in 5s", exc)
            await asyncio.sleep(5)
        except Exception:
            log.exception("data-engine session crashed, retrying in 15s")
            await asyncio.sleep(15)


if __name__ == "__main__":
    asyncio.run(main())
