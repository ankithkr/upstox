"""Orchestrates one trading day's top-down funnel, streaming.

Ported from the per-day walk in the legacy src/backtest/snapshots.py's
`compute_day_snapshots` (steps 1-3: regime gate, sector selection,
stock selection), restructured to resolve once enough live candles
have arrived instead of indexing a precomputed day's candles.

Every instrument's candles are buffered as they arrive, regardless of
whether the day plan has resolved yet, so that once the 09:30 snapshot
is available and a stock qualifies, its SymbolTracker can be backfilled
with the opening-range candles it already missed.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from shared.universe import INDEX_CONSTITUENTS, NIFTY_50_INSTRUMENT_KEY, SECTOR_INDEX_INSTRUMENT_KEYS, V2_SECTORS

from .breakout_tracker import Breakout, SymbolTracker
from .history import History
from .live_reference import latest_close, latest_trend_pct, live_opening_volume_ratio
from .params import StrategyParams
from .percentage import pct_change
from .regime_gate import LONG, evaluate_gate, pick_direction

log = logging.getLogger("strategy-engine.day_plan")

# How many candles make up the 09:15-09:30 snapshot (stock change is the
# 3rd 5-min candle's close, per snapshots.py's `_stock_snapshots`).
SNAPSHOT_CANDLES = 3


class DayPlan:
    def __init__(self, history: History, symbol_keys: dict[str, str], params: StrategyParams):
        self.history = history
        self.symbol_keys = symbol_keys  # trading_symbol -> instrument_key
        self.key_to_symbol = {v: k for k, v in symbol_keys.items()}
        self.params = params

        self._buffer: dict[str, list[tuple]] = defaultdict(list)
        self.resolved = False
        self.direction: str | None = None
        self.gate_ok: bool | None = None
        self.gate_reasons: list[str] = []
        self.selected_sectors: list[str] = []
        self.trackers: dict[str, SymbolTracker] = {}  # trading_symbol -> tracker

        self._sector_keys = {SECTOR_INDEX_INSTRUMENT_KEYS[s]: s for s in V2_SECTORS if s in SECTOR_INDEX_INSTRUMENT_KEYS}
        self._stock_keys = {key for key in symbol_keys.values()}

    def feed_candle(self, instrument_key: str, candle: tuple) -> Breakout | None:
        self._buffer[instrument_key].append(candle)

        if not self.resolved:
            if self._ready_to_resolve():
                self._resolve()
            return None

        symbol = self.key_to_symbol.get(instrument_key)
        tracker = self.trackers.get(symbol) if symbol else None
        if tracker is None:
            return None
        return tracker.on_candle(candle)

    def _ready_to_resolve(self) -> bool:
        if len(self._buffer[NIFTY_50_INSTRUMENT_KEY]) < SNAPSHOT_CANDLES:
            return False
        for key in self._sector_keys:
            if len(self._buffer[key]) < SNAPSHOT_CANDLES:
                return False
        for key in self._stock_keys:
            symbol = self.key_to_symbol.get(key)
            if symbol in self.history.stock_daily and len(self._buffer[key]) < SNAPSHOT_CANDLES:
                return False
        return True

    def _resolve(self) -> None:
        self.resolved = True

        nifty_candles = self._buffer[NIFTY_50_INSTRUMENT_KEY]
        nifty_prev = latest_close(self.history.nifty_daily)
        if nifty_prev is None:
            self.gate_ok, self.gate_reasons = False, ["no NIFTY previous close in history"]
            log.warning("day plan: no NIFTY previous close, day is closed")
            return

        nifty_change = pct_change(nifty_candles[SNAPSHOT_CANDLES - 1][4], nifty_prev)
        self.direction = pick_direction(nifty_change, self.params)
        vix = latest_close(self.history.vix_daily)
        nifty_trend = latest_trend_pct(self.history.nifty_daily)
        self.gate_ok, self.gate_reasons = evaluate_gate(self.direction, vix, nifty_trend, self.params)
        log.info(
            "day plan: nifty_change=%.2f%% direction=%s gate_ok=%s reasons=%s",
            nifty_change, self.direction, self.gate_ok, self.gate_reasons,
        )
        if not self.gate_ok:
            return

        sign = 1 if self.direction == LONG else -1
        sector_changes: dict[str, float] = {}
        for key, name in self._sector_keys.items():
            candles = self._buffer.get(key)
            if not candles or len(candles) < SNAPSHOT_CANDLES:
                continue
            prev = latest_close(self.history.sector_daily[name])
            if prev is None:
                continue
            sector_changes[name] = pct_change(candles[SNAPSHOT_CANDLES - 1][4], prev)

        eligible = [n for n, c in sector_changes.items() if sign * c > self.params.sector_band_pct]
        self.selected_sectors = sorted(eligible, key=lambda n: sign * sector_changes[n], reverse=True)[
            : self.params.top_sectors
        ]
        log.info("day plan: selected sectors=%s (of %d eligible)", self.selected_sectors, len(eligible))

        seen: set[str] = set()
        for name in self.selected_sectors:
            for symbol in INDEX_CONSTITUENTS.get(name, []):
                if symbol in seen:
                    continue
                seen.add(symbol)
                tracker = self._qualify_stock(symbol, sign)
                if tracker is not None:
                    self.trackers[symbol] = tracker
        log.info("day plan: %d stock(s) qualified: %s", len(self.trackers), list(self.trackers))

    def _qualify_stock(self, symbol: str, sign: int) -> SymbolTracker | None:
        key = self.symbol_keys.get(symbol)
        if key is None:
            return None
        candles = self._buffer.get(key)
        if not candles or len(candles) < SNAPSHOT_CANDLES:
            return None
        volume_profile = self.history.stock_volume.get(symbol)
        daily = self.history.stock_daily.get(symbol)
        if volume_profile is None or daily is None:
            return None
        prev = latest_close(daily)
        if prev is None:
            return None

        stock_change = pct_change(candles[SNAPSHOT_CANDLES - 1][4], prev)
        if sign * stock_change <= 0:
            return None
        if sign * stock_change < self.params.stock_min_move_pct or abs(stock_change) > self.params.stock_max_move_pct:
            return None

        opening_volume = sum(c[5] for c in candles[:SNAPSHOT_CANDLES])
        ratio = live_opening_volume_ratio(volume_profile, opening_volume)
        if ratio is None or ratio < self.params.min_opening_volume_ratio:
            return None

        tracker = SymbolTracker(symbol=symbol, direction=self.direction, params=self.params)
        for candle in candles:
            tracker.on_candle(candle)
        return tracker
