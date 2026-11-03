"""Response models for Supabase tables that don't already have a shared
model (equity_snapshots, strategy_configs) - these are api-gateway's own
view, not cross-service contracts, so they live here rather than in
packages/shared.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class EquitySnapshotOut(BaseModel):
    ts: datetime
    equity: float
    cash: float
    open_risk: float = 0.0


class StrategyConfigOut(BaseModel):
    version: str
    params: dict
    created_at: datetime
