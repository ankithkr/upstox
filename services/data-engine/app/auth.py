"""Reads the current Upstox access token.

Primary source: Supabase's upstox_tokens table, written by api-gateway's
"Connect Upstox" flow (services/api-gateway/app/upstox_auth.py) - this
is what a deployed data-engine (no shared filesystem with api-gateway)
reads. Falls back to a locally mounted token file for plain local dev
(e.g. tools/upstox_login.py's output) when Supabase has nothing or
isn't configured.

Either way the token still expires daily (Upstox/SEBI require a fresh
login each trading day) - this module only reads whichever is freshest,
it never refreshes one itself.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from shared.db import get_supabase

log = logging.getLogger("data-engine.auth")


def _load_from_supabase() -> str | None:
    try:
        client = get_supabase()
        resp = client.table("upstox_tokens").select("access_token").order("obtained_at", desc=True).limit(1).execute()
        rows = resp.data or []
        return rows[0]["access_token"] if rows else None
    except Exception:
        log.warning("could not read upstox_tokens from Supabase, falling back to the local file", exc_info=True)
        return None


def _load_from_file() -> str:
    path = Path(os.environ.get("UPSTOX_TOKEN_FILE", "token.json"))
    if not path.exists():
        raise RuntimeError(
            f"No Upstox token in Supabase and no local token file at {path}. "
            "Log in via the dashboard's Connect Upstox button, or run "
            "tools/upstox_login.py for local-only dev."
        )
    data = json.loads(path.read_text())
    token = data.get("access_token")
    if not token:
        raise RuntimeError(f"{path} has no 'access_token' field")
    return token


def load_access_token() -> str:
    return _load_from_supabase() or _load_from_file()
