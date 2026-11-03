"""Top up the candle cache with everything since the last cached day.

Fetches only what's missing for the v2 strategy's inputs - NIFTY 50,
India VIX, the liquid sector indices and the 120-stock universe - up to
yesterday, so `precompute_ui.py` / the backtest cover recent sessions.
Resumable and throttled (Upstox rate-limits historical candles).

    python refresh_cache.py

Needs a valid Upstox token in token.json (see `python upstox_auth.py`);
if the daily access token has lapsed it falls back to the long-lived
read-only `extended_token` stored beside it, which is enough for data.
"""

import json
import time
from datetime import date, timedelta

import requests

import src.integrations.upstox_history as H
from src.config import UPSTOX_TOKEN_FILE
from src.data.indices import NIFTY_50_INSTRUMENT_KEY, SECTOR_INDEX_INSTRUMENT_KEYS
from src.data.universe import LIQUID_UNIVERSE, V2_SECTORS, VIX_INSTRUMENT_KEY
from src.integrations.candle_cache import read_cached
from src.integrations.upstox_instruments import build_equity_symbol_index, load_instrument_master

THROTTLE_S = 0.9
DAILY_OVERLAP_DAYS = 5  # refetch a few days so a half-formed last candle gets replaced


def _pick_token() -> str:
    with open(UPSTOX_TOKEN_FILE) as f:
        data = json.load(f)
    probe = "https://api.upstox.com/v3/historical-candle/NSE_INDEX%7CNifty%2050/days/1/2026-01-02/2026-01-01"
    for name in ("access_token", "extended_token"):
        token = data.get(name)
        if not token:
            continue
        r = requests.get(probe, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
        if r.status_code != 401:
            return token
    raise SystemExit("No working Upstox token - run `python upstox_auth.py` first.")


def _last_day(key: str, unit: str, interval: str) -> date | None:
    candles = read_cached(key, unit, interval)
    return date.fromisoformat(candles[-1][0][:10]) if candles else None


def main():
    token = _pick_token()
    H.load_access_token = lambda: token
    H.OFFLINE = False
    original = H._fetch_chunk
    count = 0

    def throttled(*args, **kwargs):
        nonlocal count
        time.sleep(THROTTLE_S)
        count += 1
        return original(*args, **kwargs)

    H._fetch_chunk = throttled

    yesterday = date.today() - timedelta(days=1)
    symbol_keys = build_equity_symbol_index(load_instrument_master())
    instruments = (
        [(NIFTY_50_INSTRUMENT_KEY, "15"), (VIX_INSTRUMENT_KEY, None)]
        + [(SECTOR_INDEX_INSTRUMENT_KEYS[s], "15") for s in V2_SECTORS]
        + [(symbol_keys[s], "5") for s in LIQUID_UNIVERSE if s in symbol_keys]
    )

    for i, (key, interval) in enumerate(instruments, 1):
        try:
            last_daily = _last_day(key, "days", "1")
            if last_daily is not None and last_daily < yesterday:
                H.get_candles(key, "days", "1", last_daily - timedelta(days=DAILY_OVERLAP_DAYS), yesterday)
            if interval:
                last = _last_day(key, "minutes", interval)
                if last is not None and last < yesterday:
                    H.get_candles(key, "minutes", interval, last + timedelta(days=1), yesterday)
        except Exception as e:  # keep going; a rerun resumes from the cache
            print(f"FAIL {key}: {e}", flush=True)
        if i % 10 == 0 or i == len(instruments):
            print(f"{i}/{len(instruments)} instruments, {count} requests", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
