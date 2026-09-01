"""Per-day sector and stock snapshots for the manual-backtest UI.

This mirrors src.backtest.runner.run_backtest, but instead of throwing
away everything that doesn't become a trade it keeps every sector and
every constituent stock, tagged with its 09:30 % change, the strategy
classification, and (where the strategy would have acted) the simulated
ORB trade. The heatmap tab renders straight off this.
"""

from datetime import date, timedelta

from src.backtest.orb_engine import LONG, SHORT, simulate_trade
from src.backtest.reference_values import (
    candles_on_day,
    prev_close,
    trading_days,
    value_at_930_from_5m,
    value_at_930_from_15m,
)
from src.calculations.percentage import pct_change
from src.data.indices import (
    NIFTY_50_INSTRUMENT_KEY,
    SECTOR_INDEX_INSTRUMENT_KEYS,
    SECTOR_INDICES,
)
from src.data.stocks import INDEX_CONSTITUENTS
from src.integrations.upstox_history import get_candles
from src.integrations.upstox_instruments import (
    build_equity_symbol_index,
    load_instrument_master,
)
from src.strategy.filters import (
    IDEAL_MOMENTUM,
    classify_sector,
    classify_stock_momentum,
)
from src.strategy.market_bias import BULLISH, NEUTRAL, get_market_bias
from src.strategy.sector_selection import DEFAULT_TOP_N, select_sectors

DAILY_LOOKBACK_BUFFER_DAYS = 10


def _load_index_history(start_date, end_date, daily_start):
    daily, intraday_15m = {}, {}
    for name in SECTOR_INDICES:
        key = SECTOR_INDEX_INSTRUMENT_KEYS[name]
        daily[name] = get_candles(key, "days", "1", daily_start, end_date)
        intraday_15m[name] = get_candles(key, "minutes", "15", start_date, end_date)
    return daily, intraday_15m


def _load_stock_history(start_date, end_date, daily_start):
    unique_symbols = sorted({s for syms in INDEX_CONSTITUENTS.values() for s in syms})
    symbol_key = build_equity_symbol_index(load_instrument_master())

    daily, intraday_5m, missing = {}, {}, []
    for symbol in unique_symbols:
        key = symbol_key.get(symbol)
        if key is None:
            missing.append(symbol)
            continue
        daily[symbol] = get_candles(key, "days", "1", daily_start, end_date)
        intraday_5m[symbol] = get_candles(key, "minutes", "5", start_date, end_date)
    return daily, intraday_5m, missing


def _stock_row(symbol, day, direction, stock_5m, stock_daily):
    day_candles = candles_on_day(stock_5m.get(symbol, []), day)
    if len(day_candles) < 4:
        return None

    s930 = value_at_930_from_5m(day_candles)
    prevc = prev_close(stock_daily.get(symbol, []), day)
    if s930 is None or prevc is None:
        return None

    change = pct_change(s930, prevc)
    momentum = classify_stock_momentum(change)
    direction_matches = (
        change > 0 if direction == LONG else change < 0
    ) if direction else None

    row = {
        "symbol": symbol,
        "change": round(change, 2),
        "momentum": momentum,
        "direction_match": direction_matches,
        "qualifies": bool(direction) and direction_matches and momentum == IDEAL_MOMENTUM,
        "trade": None,
    }

    if row["qualifies"]:
        opening_high = max(c[2] for c in day_candles[:3])
        opening_low = min(c[3] for c in day_candles[:3])
        trade = simulate_trade(direction, opening_high, opening_low, day_candles[3:])
        if trade is not None:
            row["trade"] = {
                "direction": trade["direction"],
                "entry_time": trade["entry_time"][11:16],
                "entry_price": round(trade["entry_price"], 2),
                "stop_loss": round(trade["stop_loss"], 2),
                "target": round(trade["target"], 2),
                "outcome": trade["outcome"],
                "exit_time": trade["exit_time"][11:16],
                "exit_price": round(trade["exit_price"], 2),
                "hold_minutes": trade["hold_minutes"],
            }
    return row


def compute_days(start_date: date, end_date: date, sector_top_n: int = DEFAULT_TOP_N) -> dict:
    daily_start = start_date - timedelta(days=DAILY_LOOKBACK_BUFFER_DAYS)

    nifty_daily = get_candles(NIFTY_50_INSTRUMENT_KEY, "days", "1", daily_start, end_date)
    nifty_15m = get_candles(NIFTY_50_INSTRUMENT_KEY, "minutes", "15", start_date, end_date)
    days = trading_days(nifty_15m)

    sector_daily, sector_15m = _load_index_history(start_date, end_date, daily_start)
    stock_daily, stock_5m, missing = _load_stock_history(start_date, end_date, daily_start)

    out = {}
    for day in days:
        nifty_930 = value_at_930_from_15m(candles_on_day(nifty_15m, day))
        nifty_prev = prev_close(nifty_daily, day)
        if nifty_930 is None or nifty_prev is None:
            continue
        nifty_change = pct_change(nifty_930, nifty_prev)
        bias = get_market_bias(nifty_change)

        sector_changes = {}
        for name in SECTOR_INDICES:
            v930 = value_at_930_from_15m(candles_on_day(sector_15m[name], day))
            prevc = prev_close(sector_daily[name], day)
            if v930 is not None and prevc is not None:
                sector_changes[name] = pct_change(v930, prevc)

        selected = set(select_sectors(sector_changes, bias, top_n=sector_top_n))
        direction = None
        if bias != NEUTRAL:
            direction = LONG if bias == BULLISH else SHORT

        sectors = []
        for name in SECTOR_INDICES:
            if name not in sector_changes:
                continue
            change = sector_changes[name]
            stocks = []
            for symbol in INDEX_CONSTITUENTS.get(name, []):
                row = _stock_row(symbol, day, direction, stock_5m, stock_daily)
                if row is not None:
                    stocks.append(row)
            sectors.append(
                {
                    "name": name,
                    "change": round(change, 2),
                    "classification": classify_sector(change),
                    "selected": name in selected,
                    "has_constituents": bool(INDEX_CONSTITUENTS.get(name)),
                    "stocks": stocks,
                }
            )

        out[day] = {
            "date": day,
            "nifty_change": round(nifty_change, 2),
            "market_bias": bias,
            "direction": direction,
            "sectors": sectors,
        }

    return {"days": out, "missing_symbols": missing, "start": str(start_date), "end": str(end_date)}
