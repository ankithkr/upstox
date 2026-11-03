"""Best-effort Supabase writes - same fallback posture as risk-engine's
equity.py: a missing/unreachable Supabase project logs a warning and
is never fatal, since execution-engine should still run (and its
in-memory Ledger still works) without it.
"""

from __future__ import annotations

import logging
from datetime import datetime

from shared.db import get_supabase
from shared.models import OrderIntent, Trade

log = logging.getLogger("execution-engine.persistence")


def upsert_order(order: OrderIntent) -> None:
    try:
        client = get_supabase()
        client.table("orders").upsert(order.model_dump(mode="json")).execute()
    except Exception:
        log.warning("could not persist order %s to Supabase", order.id, exc_info=True)


def upsert_trade(trade: Trade) -> None:
    try:
        client = get_supabase()
        client.table("trades").upsert(trade.model_dump(mode="json")).execute()
    except Exception:
        log.warning("could not persist trade %s to Supabase", trade.id, exc_info=True)


def write_equity_snapshot(ts: datetime, equity: float, cash: float, open_risk: float = 0.0) -> None:
    try:
        client = get_supabase()
        client.table("equity_snapshots").insert(
            {"ts": ts.isoformat(), "equity": equity, "cash": cash, "open_risk": open_risk}
        ).execute()
    except Exception:
        log.warning("could not write equity snapshot to Supabase", exc_info=True)
