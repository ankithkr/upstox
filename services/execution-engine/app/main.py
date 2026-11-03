"""execution-engine: owns the Broker interface, runs PaperBroker today.

Skeleton only (Phase 5 fills this in):
  - subscribe to the `orders` Redis channel from risk-engine
  - hand each sized order to the active Broker implementation (PaperBroker
    for now; a future UpstoxLiveBroker implements the same interface)
  - persist the resulting trade lifecycle (OPEN/CLOSED/SKIPPED) to Supabase
"""

from __future__ import annotations

import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("execution-engine")


async def main() -> None:
    log.info("execution-engine starting (skeleton - PaperBroker not wired up yet)")
    while True:
        await asyncio.sleep(60)
        log.info("execution-engine heartbeat")


if __name__ == "__main__":
    asyncio.run(main())
