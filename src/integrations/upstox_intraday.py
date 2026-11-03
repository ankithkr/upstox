import time
from urllib.parse import quote

import requests

from src.integrations.upstox_auth import load_access_token

INTRADAY_URL = "https://api.upstox.com/v3/historical-candle/intraday"

RATE_LIMIT_RETRIES = 3
RATE_LIMIT_BACKOFF_SECONDS = 2


def get_intraday_candles(instrument_key: str, unit: str, interval: str) -> list[tuple]:
    """Today's candles so far for one instrument (includes the still-forming one).

    Same shape as upstox_history.get_candles: (timestamp, open, high, low,
    close, volume) tuples, oldest first. Never cached - it changes every
    candle.
    """
    url = f"{INTRADAY_URL}/{quote(instrument_key, safe='')}/{unit}/{interval}"
    headers = {"Authorization": f"Bearer {load_access_token()}", "Accept": "application/json"}

    for attempt in range(1, RATE_LIMIT_RETRIES + 1):
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 429 and attempt < RATE_LIMIT_RETRIES:
            time.sleep(RATE_LIMIT_BACKOFF_SECONDS)
            continue
        if resp.status_code == 401:
            raise RuntimeError("Upstox token expired - run `python upstox_auth.py` and log in again")
        resp.raise_for_status()
        return [tuple(c[:6]) for c in reversed(resp.json()["data"]["candles"])]

    return []
