"""risk-engine: position sizing, capital checks, daily trade cap.

Skeleton only (Phase 4 fills this in):
  - subscribe to the `signals` Redis channel from strategy-engine
  - read current equity/open-risk from Supabase
  - size the order (1% risk, no leverage, qty capped by free cash)
  - enforce the max-3-trades-a-day limit
  - publish sized order intents to the `orders` Redis channel for execution-engine
"""

from __future__ import annotations

import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("risk-engine")


async def main() -> None:
    log.info("risk-engine starting (skeleton - sizing logic not wired up yet)")
    while True:
        await asyncio.sleep(60)
        log.info("risk-engine heartbeat")


if __name__ == "__main__":
    asyncio.run(main())
