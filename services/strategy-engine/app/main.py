"""strategy-engine: the ported v2 ORB rules.

Skeleton only (Phase 3 fills this in):
  - subscribe to the `candles` Redis channel from data-engine
  - apply the regime gate (NIFTY bias, VIX, 20-day trend), sector filter,
    stock filter and breakout entry logic (ported from the legacy
    src/strategy + src/backtest modules on the `legacy/pre-rebuild` branch)
  - publish qualifying signals to the `signals` Redis channel for risk-engine
"""

from __future__ import annotations

import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("strategy-engine")


async def main() -> None:
    log.info("strategy-engine starting (skeleton - rules not ported yet)")
    while True:
        await asyncio.sleep(60)
        log.info("strategy-engine heartbeat")


if __name__ == "__main__":
    asyncio.run(main())
