"""Loads the cached candle history strategy-engine needs for the 20-day
norms (NIFTY/sector/stock trend, ATR, volume ratios). Ported from the
legacy src/backtest/history.py, pointed at the shared universe data and
this service's own candle_cache/instruments modules.

Built once per process (and re-buildable once per day, since
refresh_cache.py tops up the cache every morning) - everything here is
look-back only, never today's live ticks.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from shared.universe import (
    LIQUID_UNIVERSE,
    NIFTY_50_INSTRUMENT_KEY,
    SECTOR_INDEX_INSTRUMENT_KEYS,
    V2_SECTORS,
    VIX_INSTRUMENT_KEY,
)

from .candle_cache import read_cached
from .features import DailyIndex, VolumeProfile
from .instruments import build_equity_symbol_index, load_instrument_master


def group_by_day(candles: list[tuple]) -> dict[str, list[tuple]]:
    grouped = defaultdict(list)
    for c in candles:
        grouped[c[0][:10]].append(c)
    return dict(grouped)


@dataclass
class History:
    nifty_15m: dict[str, list[tuple]]
    nifty_daily: DailyIndex
    vix_daily: DailyIndex
    sector_15m: dict[str, dict[str, list[tuple]]]
    sector_daily: dict[str, DailyIndex]
    stock_5m: dict[str, dict[str, list[tuple]]]
    stock_daily: dict[str, DailyIndex]
    stock_volume: dict[str, VolumeProfile]
    missing_symbols: list[str] = field(default_factory=list)

    @property
    def days(self) -> list[str]:
        return sorted(self.nifty_15m)


def _symbol_keys() -> dict[str, str]:
    return build_equity_symbol_index(load_instrument_master())


def load_history(universe: list[str] = LIQUID_UNIVERSE, sectors: list[str] = V2_SECTORS) -> History:
    keys = _symbol_keys()
    stock_5m, stock_daily, stock_volume, missing = {}, {}, {}, []
    for symbol in universe:
        key = keys.get(symbol)
        candles = read_cached(key, "minutes", "5") if key else []
        if not candles:
            missing.append(symbol)
            continue
        stock_5m[symbol] = group_by_day(candles)
        stock_daily[symbol] = DailyIndex(read_cached(key, "days", "1"))
        stock_volume[symbol] = VolumeProfile(stock_5m[symbol])

    return History(
        nifty_15m=group_by_day(read_cached(NIFTY_50_INSTRUMENT_KEY, "minutes", "15")),
        nifty_daily=DailyIndex(read_cached(NIFTY_50_INSTRUMENT_KEY, "days", "1")),
        vix_daily=DailyIndex(read_cached(VIX_INSTRUMENT_KEY, "days", "1")),
        sector_15m={s: group_by_day(read_cached(SECTOR_INDEX_INSTRUMENT_KEYS[s], "minutes", "15")) for s in sectors},
        sector_daily={s: DailyIndex(read_cached(SECTOR_INDEX_INSTRUMENT_KEYS[s], "days", "1")) for s in sectors},
        stock_5m=stock_5m,
        stock_daily=stock_daily,
        stock_volume=stock_volume,
        missing_symbols=missing,
    )
