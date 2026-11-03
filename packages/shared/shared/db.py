"""Supabase client factory shared by risk-engine, execution-engine and
api-gateway. Uses the service-role key - these are trusted backend
services, not the browser, so RLS is bypassed by design."""

from __future__ import annotations

import os
from functools import lru_cache

from supabase import Client, create_client


@lru_cache(maxsize=1)
def get_supabase() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return create_client(url, key)
