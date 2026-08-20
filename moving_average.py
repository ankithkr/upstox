import datetime
from urllib.parse import quote

import requests

HISTORICAL_URL = "https://api.upstox.com/v3/historical-candle/{instrument_key}/days/1/{to_date}/{from_date}"


def fetch_20_day_average(instrument_key, access_token, lookback_days=35):
    to_date = datetime.date.today()
    from_date = to_date - datetime.timedelta(days=lookback_days)

    url = HISTORICAL_URL.format(
        instrument_key=quote(instrument_key, safe=""),
        to_date=to_date.isoformat(),
        from_date=from_date.isoformat(),
    )
    response = requests.get(
        url,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
        },
    )
    response.raise_for_status()
    candles = response.json()["data"]["candles"]

    # keep only days with real trading activity (volume > 0), most recent first
    traded_days = sorted(
        (c for c in candles if c[5] > 0),
        key=lambda c: c[0],
        reverse=True,
    )

    last_20 = traded_days[:20]
    if not last_20:
        return None

    closes = [c[4] for c in last_20]
    return sum(closes) / len(closes)
