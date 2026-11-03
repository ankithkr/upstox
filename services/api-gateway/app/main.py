"""api-gateway: the only service the frontend talks to.

Skeleton only (Phase 6 fills this in):
  - REST endpoints: live positions, trade log, equity curve, strategy config
  - a WebSocket for pushing live updates to the dashboard
  - control endpoints: start/stop the paper-trading session
All of it reads from Supabase; it never talks to Redis directly.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="paper-trading api-gateway")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO narrow to the deployed frontend origin before going live
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
