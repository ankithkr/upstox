"""Resolves Upstox instrument keys (as published on the `candles` Redis
channel) back to trading symbols (as carried on OrderIntent/Trade).
Same local-instrument-master read as strategy-engine's instruments.py -
duplicated rather than shared because it's a thin, service-local I/O
helper, not a cross-service contract.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def load_instrument_master() -> list[dict]:
    path = Path(os.environ.get("INSTRUMENT_MASTER_FILE", "instruments_nse.json"))
    if not path.exists():
        raise RuntimeError(
            f"Instrument master not found at {path}. Run fetch_history.py "
            "(legacy/pre-rebuild) at least once to create it."
        )
    with open(path) as f:
        return json.load(f)


def build_key_to_symbol_index(instruments: list[dict]) -> dict[str, str]:
    """instrument_key -> trading_symbol, for NSE cash-market equities only."""
    return {
        d["instrument_key"]: d["trading_symbol"]
        for d in instruments
        if d.get("segment") == "NSE_EQ" and d.get("instrument_type") == "EQ"
    }
