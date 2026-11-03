"""Reads the most recent equity snapshot so risk-engine knows today's
starting capital. Falls back to PAPER_CAPITAL when there's no Supabase
project wired up yet (or the read fails) - this should not be the
long-term behaviour once execution-engine is writing real snapshots
(Phase 5), but it means risk-engine doesn't hard-depend on Supabase
being live to be testable now.
"""

from __future__ import annotations

import logging

from shared.db import get_supabase

log = logging.getLogger("risk-engine.equity")


def latest_equity(default: float) -> float:
    try:
        client = get_supabase()
        resp = client.table("equity_snapshots").select("equity").order("ts", desc=True).limit(1).execute()
        rows = resp.data
        if rows:
            return float(rows[0]["equity"])
    except Exception:
        log.warning("could not read equity_snapshots from Supabase, using default %.2f", default, exc_info=True)
    return default
