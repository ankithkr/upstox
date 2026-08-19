import gzip
import json
import os
import time

import requests

INSTRUMENTS_URL = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
INSTRUMENTS_CACHE_FILE = "instruments_nse.json"
CACHE_MAX_AGE_SECONDS = 24 * 60 * 60

_instruments_cache = None


def _load_instruments():
    global _instruments_cache
    if _instruments_cache is not None:
        return _instruments_cache

    if os.path.exists(INSTRUMENTS_CACHE_FILE) and \
            time.time() - os.path.getmtime(INSTRUMENTS_CACHE_FILE) < CACHE_MAX_AGE_SECONDS:
        with open(INSTRUMENTS_CACHE_FILE, "r") as f:
            _instruments_cache = json.load(f)
        return _instruments_cache

    response = requests.get(INSTRUMENTS_URL)
    response.raise_for_status()
    instruments = json.loads(gzip.decompress(response.content))

    with open(INSTRUMENTS_CACHE_FILE, "w") as f:
        json.dump(instruments, f)

    _instruments_cache = instruments
    return instruments


def resolve_instrument_key(trading_symbol, segment="NSE_EQ"):
    for entry in _load_instruments():
        if entry.get("segment") == segment and entry.get("trading_symbol") == trading_symbol:
            return entry["instrument_key"]
    raise ValueError(f"Instrument not found: {trading_symbol} on {segment}")
