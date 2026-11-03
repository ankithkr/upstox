"""Backfill multi-year candles into data_cache/candles for the research harness.

Resumable (cached chunks are skipped) and throttled to stay under Upstox's
historical-candle rate limits. Run:  python fetch_history.py
Intraday history before the existing cache window is fetched as
[INTRADAY_START, INTRADAY_END]; the existing window is left alone.
"""

import statistics
import sys
import time
from datetime import date

import src.integrations.upstox_history as H
from src.data.indices import NIFTY_50_INSTRUMENT_KEY, SECTOR_INDEX_INSTRUMENT_KEYS
from src.data.stocks import INDEX_CONSTITUENTS
from src.integrations.upstox_instruments import build_equity_symbol_index, load_instrument_master

DAILY_START, DAILY_END = date(2022, 12, 1), date(2026, 10, 7)
INTRADAY_START, INTRADAY_END = date(2023, 1, 2), date(2026, 2, 19)
UNIVERSE_SIZE = 120
VIX_KEY = "NSE_INDEX|India VIX"
THROTTLE_S = 0.9
# Liquid sector indices only; the mid/small-cap ones add requests but no tradable names.
SECTORS = [
    "NIFTY AUTO", "NIFTY BANK", "NIFTY FINANCIAL SERVICES", "NIFTY FMCG", "NIFTY IT",
    "NIFTY MEDIA", "NIFTY METAL", "NIFTY PHARMA", "NIFTY PSU BANK", "NIFTY REALTY",
    "NIFTY PRIVATE BANK", "NIFTY HEALTHCARE", "NIFTY CONSUMER DURABLES", "NIFTY OIL & GAS",
    "NIFTY FINANCIAL SERVICES EX-BANK", "NIFTY CEMENT",
]

H.OFFLINE = False
_orig = H._fetch_chunk
requests_made = 0


def _throttled(*a, **kw):
    global requests_made
    time.sleep(THROTTLE_S)
    requests_made += 1
    if requests_made % 100 == 0:
        print(f"  ...{requests_made} requests", flush=True)
    return _orig(*a, **kw)


H._fetch_chunk = _throttled


def safe(label, fn):
    try:
        return fn()
    except Exception as e:  # keep going; rerun resumes from cache
        print(f"FAIL {label}: {e}", flush=True)
        return None


def main():
    symbol_key = build_equity_symbol_index(load_instrument_master())
    symbols = sorted({s for v in INDEX_CONSTITUENTS.values() for s in v})

    print("daily: nifty / vix / sectors / stocks", flush=True)
    for key in [NIFTY_50_INSTRUMENT_KEY, VIX_KEY] + [SECTOR_INDEX_INSTRUMENT_KEYS[s] for s in SECTORS]:
        safe(key, lambda k=key: H.get_candles(k, "days", "1", DAILY_START, DAILY_END))
    turnover = {}
    for s in symbols:
        if s not in symbol_key:
            continue
        c = safe(s, lambda s=s: H.get_candles(symbol_key[s], "days", "1", DAILY_START, DAILY_END))
        if c and len(c) > 250:
            turnover[s] = statistics.median(x[4] * x[5] for x in c[-250:])
    universe = sorted(turnover, key=turnover.get, reverse=True)[:UNIVERSE_SIZE]
    print(f"universe: {len(universe)} stocks", flush=True)
    with open("data_cache/research_universe.txt", "w") as f:
        f.write("\n".join(universe))

    print("intraday: nifty + sectors (15m)", flush=True)
    for key in [NIFTY_50_INSTRUMENT_KEY] + [SECTOR_INDEX_INSTRUMENT_KEYS[s] for s in SECTORS]:
        safe(key, lambda k=key: H.get_candles(k, "minutes", "15", INTRADAY_START, INTRADAY_END))
    print("intraday: stocks (5m)", flush=True)
    for i, s in enumerate(universe, 1):
        safe(s, lambda s=s: H.get_candles(symbol_key[s], "minutes", "5", INTRADAY_START, INTRADAY_END))
        print(f"{i}/{len(universe)} {s} ({requests_made} req)", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    sys.exit(main())
