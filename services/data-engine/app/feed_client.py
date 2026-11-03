"""Upstox Market Data Feed V3 client: authorize, connect, subscribe, decode.

Protocol, confirmed against Upstox's own docs and proto file (not guessed):
  - GET https://api.upstox.com/v3/feed/market-data-feed/authorize
    with Authorization: Bearer <token>, Accept: application/json
    -> {"status": "success", "data": {"authorized_redirect_uri": "wss://..."}}
  - Connect to that wss:// URL (single-use, short-lived).
  - Subscription request is JSON, sent as a BINARY frame (not text):
    {"guid": "...", "method": "sub", "data": {"mode": "ltpc", "instrumentKeys": [...]}}
  - Server pushes binary-encoded FeedResponse protobuf messages (see
    ../proto/MarketDataFeed.proto); websockets answers ping frames with
    pong automatically.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator

import httpx
import websockets

from . import MarketDataFeed_pb2 as pb

AUTHORIZE_URL = "https://api.upstox.com/v3/feed/market-data-feed/authorize"

log = logging.getLogger("data-engine.feed_client")


async def get_authorized_ws_url(access_token: str) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            AUTHORIZE_URL,
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["data"]["authorized_redirect_uri"]


async def stream_feed(
    ws_url: str, instrument_keys: list[str], mode: str = "ltpc"
) -> AsyncIterator[pb.FeedResponse]:
    async with websockets.connect(ws_url, max_size=None) as ws:
        subscribe_msg = {
            "guid": str(uuid.uuid4()),
            "method": "sub",
            "data": {"mode": mode, "instrumentKeys": instrument_keys},
        }
        await ws.send(json.dumps(subscribe_msg).encode("utf-8"))
        log.info("subscribed to %d instrument keys in %s mode", len(instrument_keys), mode)

        async for raw in ws:
            if not isinstance(raw, bytes):
                continue
            feed = pb.FeedResponse()
            feed.ParseFromString(raw)
            yield feed
