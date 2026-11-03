"""Redis pub/sub backbone shared by every engine.

One channel per hop in the pipeline:
    data-engine --CANDLES--> strategy-engine --SIGNALS--> risk-engine --ORDERS--> execution-engine

Every engine imports the channel name from here rather than hardcoding the
string, and uses `publish`/`subscribe` rather than talking to redis-py
directly, so the wire format (JSON-encoded Pydantic models) stays in one
place.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

from pydantic import BaseModel
from redis.asyncio import Redis

CHANNEL_CANDLES = "candles"
CHANNEL_SIGNALS = "signals"
CHANNEL_ORDERS = "orders"


def get_redis() -> Redis:
    url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    return Redis.from_url(url, decode_responses=True)


async def publish(redis: Redis, channel: str, message: BaseModel) -> None:
    await redis.publish(channel, message.model_dump_json())


async def subscribe(redis: Redis, channel: str) -> AsyncIterator[str]:
    """Yields raw JSON payloads published on `channel`; caller parses into
    the model it expects (Candle on CHANNEL_CANDLES, Signal on
    CHANNEL_SIGNALS, OrderIntent on CHANNEL_ORDERS)."""
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)
    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            yield message["data"]
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
