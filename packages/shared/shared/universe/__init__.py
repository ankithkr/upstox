"""The v2 strategy's universe: sector indices, their constituent stocks,
and the 120-stock liquid universe. Ported verbatim from the legacy
src/data/{indices,stocks,universe}.py on `legacy/pre-rebuild` - pure
data, no behaviour, shared by data-engine (what to subscribe to) and
strategy-engine (how to apply the top-down filters)."""

from .indices import (
    NIFTY_50_INSTRUMENT_KEY,
    NIFTY_50_NAME,
    SECTOR_INDEX_INSTRUMENT_KEYS,
    SECTOR_INDICES,
)
from .liquid import LIQUID_UNIVERSE, V2_SECTORS, VIX_INSTRUMENT_KEY
from .stocks import INDEX_CONSTITUENTS

__all__ = [
    "NIFTY_50_INSTRUMENT_KEY",
    "NIFTY_50_NAME",
    "SECTOR_INDEX_INSTRUMENT_KEYS",
    "SECTOR_INDICES",
    "LIQUID_UNIVERSE",
    "V2_SECTORS",
    "VIX_INSTRUMENT_KEY",
    "INDEX_CONSTITUENTS",
]
