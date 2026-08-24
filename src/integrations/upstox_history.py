import csv
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote

import requests

from src.integrations.upstox_auth import load_access_token

HISTORY_URL = "https://api.upstox.com/v3/historical-candle"
CACHE_DIR = Path("data_cache/candles")

# Upstox caps 1-15 minute (and hourly) candle requests to ~1 calendar
# month of range per call; 28 days stays safely under that regardless
# of month length. Daily/weekly/monthly candles have no such cap.
CHUNK_DAYS = 28
CHUNKED_UNITS = ("minutes", "hours")

RATE_LIMIT_RETRIES = 5
RATE_LIMIT_BACKOFF_SECONDS = 15


def _cache_path(instrument_key, unit, interval, chunk_from, chunk_to):
    safe_key = "".join(c if c.isalnum() else "_" for c in instrument_key)
    filename = f"{safe_key}_{unit}_{interval}_{chunk_from}_{chunk_to}.csv"
    return CACHE_DIR / filename


def _read_cache(path):
    if not path.exists():
        return None
    with open(path, newline="") as f:
        reader = csv.reader(f)
        next(reader)
        return [
            (row[0], float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5]))
            for row in reader
        ]


def _write_cache(path, candles):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        writer.writerows(candles)


def _fetch_chunk(instrument_key, unit, interval, chunk_from, chunk_to, token):
    quoted_key = quote(instrument_key, safe="")
    url = f"{HISTORY_URL}/{quoted_key}/{unit}/{interval}/{chunk_to}/{chunk_from}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    for attempt in range(1, RATE_LIMIT_RETRIES + 1):
        resp = requests.get(url, headers=headers)
        if resp.status_code == 429 and attempt < RATE_LIMIT_RETRIES:
            time.sleep(RATE_LIMIT_BACKOFF_SECONDS)
            continue
        resp.raise_for_status()
        return resp.json()["data"]["candles"]

    return []


def get_candles(
    instrument_key: str, unit: str, interval: str, start_date: date, end_date: date
) -> list[tuple]:
    """Historical candles for one instrument over [start_date, end_date].

    Minute/hour candles are chunked into <=28-day windows to stay under
    Upstox's per-request cap; daily/weekly/monthly candles are fetched
    in a single call. Each chunk is cached locally as CSV so reruns
    don't refetch. Returns (timestamp, open, high, low, close, volume)
    tuples, oldest first.
    """
    token = load_access_token()
    chunk_days = CHUNK_DAYS if unit in CHUNKED_UNITS else None

    all_candles = []
    current_start = start_date
    while current_start <= end_date:
        chunk_end = (
            min(current_start + timedelta(days=chunk_days - 1), end_date)
            if chunk_days
            else end_date
        )

        path = _cache_path(instrument_key, unit, interval, current_start, chunk_end)
        cached = _read_cache(path)
        if cached is None:
            raw = _fetch_chunk(instrument_key, unit, interval, current_start, chunk_end, token)
            cached = [tuple(c[:6]) for c in reversed(raw)]
            _write_cache(path, cached)

        all_candles.extend(cached)
        current_start = chunk_end + timedelta(days=1)

    all_candles.sort(key=lambda c: c[0])
    return all_candles
