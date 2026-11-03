"""Publishes the active StrategyParams to Supabase on startup, so
api-gateway's /strategy-config has something real to show - best-effort,
same fallback posture as every other Supabase write in this project.
"""

from __future__ import annotations

import logging

from shared.db import get_supabase

from .params import StrategyParams

log = logging.getLogger("strategy-engine.config_publisher")

VERSION = "v2"


def publish_active_config(params: StrategyParams) -> None:
    try:
        client = get_supabase()
        client.table("strategy_configs").insert({"version": VERSION, "params": params.as_dict()}).execute()
    except Exception:
        log.warning("could not publish strategy config to Supabase", exc_info=True)
