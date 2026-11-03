"""api-gateway: the only service the frontend talks to.

Pure REST over Supabase for now (no WebSocket yet - there's no live
engine chain running against a real Supabase project to push updates
from, so a poll-based dashboard is the honest v1; see README for what's
still aspirational: push updates and start/stop controls, since no
engine currently exposes a control channel to start/stop against).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shared.models import Trade

from . import queries
from .schemas import EquitySnapshotOut, StrategyConfigOut
from .upstox_auth import router as upstox_auth_router

app = FastAPI(title="paper-trading api-gateway")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO narrow to the deployed frontend origin before going live
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upstox_auth_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/trades", response_model=list[Trade])
async def list_trades(date: str | None = None, status: str | None = None, limit: int = 200) -> list[dict]:
    return queries.fetch_trades(date=date, status=status, limit=limit)


@app.get("/positions", response_model=list[Trade])
async def list_positions() -> list[dict]:
    return queries.fetch_positions()


@app.get("/equity-curve", response_model=list[EquitySnapshotOut])
async def equity_curve(limit: int = 500) -> list[dict]:
    return queries.fetch_equity_curve(limit=limit)


@app.get("/strategy-config", response_model=StrategyConfigOut | None)
async def strategy_config() -> dict | None:
    return queries.fetch_latest_strategy_config()
