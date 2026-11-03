"""data-engine: Upstox WebSocket feed -> 5-min candle aggregation -> Redis publish.

Skeleton only (Phase 2 fills this in):
  - connect to Upstox WebSocket during market hours (09:00-15:30 IST, NSE trading days)
  - aggregate ticks into closed 5-min / 15-min candles
  - publish each closed candle to the `candles` Redis channel for strategy-engine
"""

from __future__ import annotations

import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("data-engine")


async def main() -> None:
    log.info("data-engine starting (skeleton - no live feed wired up yet)")
    while True:
        await asyncio.sleep(60)
        log.info("data-engine heartbeat")


if __name__ == "__main__":
    asyncio.run(main())
