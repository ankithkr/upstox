import requests

from src.integrations.upstox_auth import load_access_token

QUOTES_URL = "https://api.upstox.com/v2/market-quote/quotes"

# Upstox rejects requests for too many instruments at once.
MAX_INSTRUMENTS_PER_REQUEST = 500


def _chunk(items, size):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def get_quotes(instrument_keys: list[str]) -> dict[str, dict]:
    """Fetch last price and previous close for a list of instrument keys.

    Returns {instrument_key: {"last_price": float, "prev_close": float}}.

    Upstox's quote response only gives last_price and net_change (today's
    move in absolute terms), not previous close directly, so it's derived
    as last_price - net_change.
    """
    token = load_access_token()
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    results: dict[str, dict] = {}
    for chunk in _chunk(instrument_keys, MAX_INSTRUMENTS_PER_REQUEST):
        resp = requests.get(
            QUOTES_URL, params={"instrument_key": ",".join(chunk)}, headers=headers
        )
        resp.raise_for_status()
        data = resp.json()["data"]

        for quote in data.values():
            instrument_key = quote["instrument_token"]
            last_price = quote["last_price"]
            net_change = quote["net_change"]
            results[instrument_key] = {
                "last_price": last_price,
                "prev_close": last_price - net_change,
            }

    return results
