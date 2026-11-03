"""Supabase reads for the frontend. Same fallback posture as the other
engines (risk-engine's equity.py, execution-engine's persistence.py):
a missing/unreachable Supabase project returns an empty result instead
of raising, so the dashboard still loads (empty) rather than erroring.
"""

from __future__ import annotations

import logging

from shared.db import get_supabase

log = logging.getLogger("api-gateway.queries")


def fetch_trades(date: str | None = None, status: str | None = None, limit: int = 200) -> list[dict]:
    try:
        client = get_supabase()
        query = client.table("trades").select("*").order("entry_time", desc=True).limit(limit)
        if status is not None:
            query = query.eq("status", status)
        resp = query.execute()
        rows = resp.data or []
    except Exception:
        log.warning("could not read trades from Supabase", exc_info=True)
        return []

    if date is not None:
        rows = [r for r in rows if (r.get("entry_time") or "").startswith(date)]
    return rows


def fetch_positions() -> list[dict]:
    return fetch_trades(status="OPEN")


def fetch_equity_curve(limit: int = 500) -> list[dict]:
    try:
        client = get_supabase()
        resp = client.table("equity_snapshots").select("*").order("ts", desc=False).limit(limit).execute()
        return resp.data or []
    except Exception:
        log.warning("could not read equity_snapshots from Supabase", exc_info=True)
        return []


def fetch_latest_strategy_config() -> dict | None:
    try:
        client = get_supabase()
        resp = client.table("strategy_configs").select("*").order("created_at", desc=True).limit(1).execute()
        rows = resp.data or []
        return rows[0] if rows else None
    except Exception:
        log.warning("could not read strategy_configs from Supabase", exc_info=True)
        return None
