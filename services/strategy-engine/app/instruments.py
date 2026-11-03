"""Resolves NSE trading symbols (e.g. "RELIANCE") to Upstox instrument
keys (e.g. "NSE_EQ|INE002A01018"), from the locally cached instrument
master. Ported from the read side of the legacy
src/integrations/upstox_instruments.py - strategy-engine never downloads
the master itself, only reads the file the legacy fetch flow produced
(mounted read-only, same as the candle cache).
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


def build_equity_symbol_index(instruments: list[dict]) -> dict[str, str]:
    """trading_symbol -> instrument_key, for NSE cash-market equities only."""
    return {
        d["trading_symbol"]: d["instrument_key"]
        for d in instruments
        if d.get("segment") == "NSE_EQ" and d.get("instrument_type") == "EQ"
    }
