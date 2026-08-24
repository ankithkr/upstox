import gzip
import json
import time
from pathlib import Path

import requests

INSTRUMENT_MASTER_URL = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
CACHE_FILE = Path("instruments_nse.json")
CACHE_MAX_AGE_SECONDS = 24 * 60 * 60


def _download_instrument_master() -> list[dict]:
    resp = requests.get(INSTRUMENT_MASTER_URL, timeout=60)
    resp.raise_for_status()
    return json.loads(gzip.decompress(resp.content))


def load_instrument_master(force_refresh: bool = False) -> list[dict]:
    """The full Upstox NSE instrument master, cached locally for a day."""
    if not force_refresh and CACHE_FILE.exists():
        age = time.time() - CACHE_FILE.stat().st_mtime
        if age < CACHE_MAX_AGE_SECONDS:
            with open(CACHE_FILE) as f:
                return json.load(f)

    instruments = _download_instrument_master()
    with open(CACHE_FILE, "w") as f:
        json.dump(instruments, f)
    return instruments


def build_equity_symbol_index(instruments: list[dict]) -> dict[str, str]:
    """trading_symbol -> instrument_key, for NSE cash-market equities only."""
    return {
        d["trading_symbol"]: d["instrument_key"]
        for d in instruments
        if d.get("segment") == "NSE_EQ" and d.get("instrument_type") == "EQ"
    }
