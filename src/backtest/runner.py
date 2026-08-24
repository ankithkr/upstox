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
from src.data.indices import NIFTY_50_INSTRUMENT_KEY, SECTOR_INDEX_INSTRUMENT_KEYS, SECTOR_INDICES
from src.data.stocks import INDEX_CONSTITUENTS
from src.integrations.upstox_history import get_candles
from src.integrations.upstox_instruments import build_equity_symbol_index, load_instrument_master
from src.strategy.filters import IDEAL_MOMENTUM, classify_stock_momentum
from src.strategy.market_bias import BULLISH, get_market_bias
from src.strategy.sector_selection import DEFAULT_TOP_N, select_sectors

# Extra history before start_date purely so the first trading day in
# range still has a prior day's close to compare against.
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

    daily, intraday_5m = {}, {}
    for symbol in unique_symbols:
        key = symbol_key[symbol]
        daily[symbol] = get_candles(key, "days", "1", daily_start, end_date)
        intraday_5m[symbol] = get_candles(key, "minutes", "5", start_date, end_date)
    return daily, intraday_5m


def run_backtest(start_date: date, end_date: date, sector_top_n: int = DEFAULT_TOP_N) -> list[dict]:
    """Run the top-down ORB strategy over [start_date, end_date].

    Returns a list of trade dicts (one per triggered entry - see
    orb_engine.simulate_trade for the shape), each tagged with the
    date, sector, symbol, market bias, and the sector/stock % change
    that qualified it.
    """
    daily_start = start_date - timedelta(days=DAILY_LOOKBACK_BUFFER_DAYS)

    nifty_daily = get_candles(NIFTY_50_INSTRUMENT_KEY, "days", "1", daily_start, end_date)
    nifty_15m = get_candles(NIFTY_50_INSTRUMENT_KEY, "minutes", "15", start_date, end_date)
    days = trading_days(nifty_15m)

    sector_daily, sector_15m = _load_index_history(start_date, end_date, daily_start)
    stock_daily, stock_5m = _load_stock_history(start_date, end_date, daily_start)

    trades = []
    for day in days:
        nifty_930 = value_at_930_from_15m(candles_on_day(nifty_15m, day))
        nifty_prev = prev_close(nifty_daily, day)
        if nifty_930 is None or nifty_prev is None:
            continue
        bias = get_market_bias(pct_change(nifty_930, nifty_prev))

        sector_changes = {}
        for name in SECTOR_INDICES:
            v930 = value_at_930_from_15m(candles_on_day(sector_15m[name], day))
            prevc = prev_close(sector_daily[name], day)
            if v930 is not None and prevc is not None:
                sector_changes[name] = pct_change(v930, prevc)

        selected_sectors = select_sectors(sector_changes, bias, top_n=sector_top_n)
        if not selected_sectors:
            continue
        direction = LONG if bias == BULLISH else SHORT

        for sector_name in selected_sectors:
            for symbol in INDEX_CONSTITUENTS.get(sector_name, []):
                day_candles = candles_on_day(stock_5m[symbol], day)
                if len(day_candles) < 4:
                    continue

                s930 = value_at_930_from_5m(day_candles)
                prevc = prev_close(stock_daily[symbol], day)
                if s930 is None or prevc is None:
                    continue
                stock_change = pct_change(s930, prevc)
                # PDF section 3's momentum table pairs bullish momentum
                # with buy trades and bearish momentum with sell trades -
                # a stock moving the "wrong" way for the sector's bias
                # doesn't qualify, even if its magnitude is in range.
                direction_matches = (
                    stock_change > 0 if direction == LONG else stock_change < 0
                )
                if not direction_matches:
                    continue
                if classify_stock_momentum(stock_change) != IDEAL_MOMENTUM:
                    continue

                opening_high = max(c[2] for c in day_candles[:3])
                opening_low = min(c[3] for c in day_candles[:3])
                trade = simulate_trade(direction, opening_high, opening_low, day_candles[3:])
                if trade is None:
                    continue

                trade.update(
                    date=day,
                    sector=sector_name,
                    symbol=symbol,
                    market_bias=bias,
                    sector_change=round(sector_changes[sector_name], 2),
                    stock_change=round(stock_change, 2),
                )
                trades.append(trade)

    return trades
