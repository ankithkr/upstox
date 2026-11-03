"""Backtest a short-strangle-plus-hedge (iron condor), weekly or monthly,
optionally with a stop-loss, on an index or an individual F&O stock.

For each cycle: pick strikes off the entry day's own realized volatility,
scaled to that cycle's actual length (see strikes.py), collect the net
credit at the entry day's settle prices, then walk the position forward
day by day. Two steps, kept separate so a stop-loss sweep doesn't have to
re-fetch or re-detect cycles for every candidate level:

  build_cycle_paths()  - the expensive part: fetch bhavcopy, detect cycles,
                          price every leg on every day of every cycle.
  apply_stop_loss()    - cheap, in-memory: given those paths, decide where
                          each cycle actually exits for a given stop-loss
                          threshold (or none - hold to expiry).

NSE sets every option's SttlmPric to the underlying's own close on expiry
day, not the contract's intrinsic value - so the expiry-day mark for each
leg is computed from the underlying's final price, not read off that
field directly.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

from src.backtest.features import DailyIndex
from src.integrations.candle_cache import read_cached
from src.integrations.nse_bhavcopy import OptionRow, fetch_fo_bhavcopy
from src.integrations.upstox_instruments import build_equity_symbol_index, load_instrument_master
from src.options.costs import buy_transaction_cost, exercise_cost, sell_transaction_cost
from src.options.strikes import condor_strikes, expected_move_pct

# bhavcopy symbol -> the Upstox index instrument_key already cached for ATR.
# Anything else is looked up as an equity via the instrument master.
INDEX_INSTRUMENT_KEYS = {
    "NIFTY": "NSE_INDEX|Nifty 50",
    "BANKNIFTY": "NSE_INDEX|Nifty Bank",
}

LEG_SIDES = {  # leg name -> (option_type, is_short)
    "short_call": ("CE", True),
    "short_put": ("PE", True),
    "hedge_call": ("CE", False),
    "hedge_put": ("PE", False),
}

_equity_symbol_keys: dict[str, str] | None = None
_BY_SYMBOL_MEMO: dict[date, dict[str, list[OptionRow]]] = {}


def _underlying_instrument_key(symbol: str) -> str | None:
    if symbol in INDEX_INSTRUMENT_KEYS:
        return INDEX_INSTRUMENT_KEYS[symbol]
    global _equity_symbol_keys
    if _equity_symbol_keys is None:
        _equity_symbol_keys = build_equity_symbol_index(load_instrument_master())
    return _equity_symbol_keys.get(symbol)


def _rows_for(trade_date: date, symbol: str) -> list[OptionRow]:
    """fetch_fo_bhavcopy(trade_date), pre-grouped by symbol and memoized -
    an O(1) lookup instead of re-scanning ~30k rows per (day, symbol) pair,
    which otherwise dominates runtime once a backtest loops over several
    symbols sharing the same date range.
    """
    by_symbol = _BY_SYMBOL_MEMO.get(trade_date)
    if by_symbol is None:
        by_symbol = {}
        for row in fetch_fo_bhavcopy(trade_date):
            by_symbol.setdefault(row.symbol, []).append(row)
        _BY_SYMBOL_MEMO[trade_date] = by_symbol
    return by_symbol.get(symbol, [])


@dataclass
class DayMark:
    day: date
    is_expiry: bool
    mark_pnl: float  # price-only P&L vs entry, before any cost
    prices: dict[str, float]  # leg -> settle (or expiry-day intrinsic value)


@dataclass
class CyclePath:
    symbol: str
    entry_date: date
    expiry_date: date
    spot_entry: float
    lot_size: int
    strikes: dict[str, float]
    entry_premiums: dict[str, float]
    entry_cost: float
    net_credit: float  # gross, before any cost
    path: list[DayMark] = field(default_factory=list)


@dataclass
class CycleResult:
    symbol: str
    entry_date: date
    expiry_date: date
    exit_date: date
    stopped_out: bool
    spot_entry: float
    lot_size: int
    strikes: dict[str, float]
    net_credit: float
    costs: float
    pnl: float


def _daily_bhavcopy_range(start: date, end: date) -> dict[date, list[OptionRow]]:
    out = {}
    d = start
    while d <= end:
        rows = fetch_fo_bhavcopy(d)
        if rows:
            out[d] = rows
        d += timedelta(days=1)
    return out


def _detect_cycles(symbol: str, rows_by_day: dict[date, list[OptionRow]]) -> list[tuple[date, date]]:
    """[(entry_date, expiry_date), ...] for every complete cycle found.

    Drops the first (already in-progress when our window starts) and the
    last (not yet resolved) partial cycles.
    """
    nearest: dict[date, date] = {}
    for d in rows_by_day:
        sym_rows = _rows_for(d, symbol)
        if sym_rows:
            nearest[d] = min(r.expiry for r in sym_rows)

    days = sorted(nearest)
    cycles: list[tuple[date, date]] = []
    cycle_start = None
    for i in range(1, len(days)):
        if nearest[days[i]] != nearest[days[i - 1]]:
            if cycle_start is not None:
                cycles.append((cycle_start, nearest[days[i - 1]]))
            cycle_start = days[i]
    return cycles


def _mark_pnl(entry_premiums: dict[str, float], prices: dict[str, float], lot_size: int) -> float:
    total = 0.0
    for leg, (_, is_short) in LEG_SIDES.items():
        diff = entry_premiums[leg] - prices[leg] if is_short else prices[leg] - entry_premiums[leg]
        total += diff * lot_size
    return total


def _exit_cost(prices: dict[str, float], lot_size: int, is_expiry: bool) -> float:
    total = 0.0
    for leg, (_, is_short) in LEG_SIDES.items():
        notional = prices[leg] * lot_size
        if is_short:
            total += 0.0 if is_expiry else buy_transaction_cost(notional)
        else:
            total += exercise_cost(notional) if is_expiry else sell_transaction_cost(notional)
    return total


def build_cycle_paths(
    symbol: str,
    start: date,
    end: date,
    k_short: float = 1.0,
    k_wing: float = 1.0,
    atr_window: int = 14,
) -> list[CyclePath]:
    instrument_key = _underlying_instrument_key(symbol)
    if instrument_key is None:
        raise ValueError(f"no instrument_key found for {symbol!r}")

    rows_by_day = _daily_bhavcopy_range(start, end)
    cycles = _detect_cycles(symbol, rows_by_day)
    vol_index = DailyIndex(read_cached(instrument_key, "days", "1"))
    trading_days = sorted(rows_by_day)

    paths = []
    for entry_date, expiry_date in cycles:
        entry_rows = [r for r in _rows_for(entry_date, symbol) if r.expiry == expiry_date]
        if not entry_rows:
            continue

        spot = next((r.underlying_price for r in entry_rows if r.underlying_price), None)
        lot_size = next((r.lot_size for r in entry_rows if r.lot_size), None)
        atr = vol_index.atr_pct(entry_date.isoformat(), window=atr_window)
        cycle_days = [d for d in trading_days if entry_date <= d <= expiry_date]
        if spot is None or lot_size is None or atr is None or len(cycle_days) < 2:
            continue

        call_strikes = sorted({r.strike for r in entry_rows if r.option_type == "CE"})
        put_strikes = sorted({r.strike for r in entry_rows if r.option_type == "PE"})
        if not call_strikes or not put_strikes:
            continue

        move_pct = expected_move_pct(atr, len(cycle_days) - 1)
        strikes = condor_strikes(spot, call_strikes, put_strikes, move_pct, k_short, k_wing)

        entry_by_key = {(r.strike, r.option_type): r for r in entry_rows}
        entry_premiums, entry_cost, missing = {}, 0.0, False
        for leg, strike in strikes.items():
            row = entry_by_key.get((strike, LEG_SIDES[leg][0]))
            if row is None:
                missing = True
                break
            entry_premiums[leg] = row.settle
            notional = row.settle * lot_size
            entry_cost += sell_transaction_cost(notional) if LEG_SIDES[leg][1] else buy_transaction_cost(notional)
        if missing:
            continue

        net_credit = (entry_premiums["short_call"] + entry_premiums["short_put"]) - (
            entry_premiums["hedge_call"] + entry_premiums["hedge_put"]
        )
        net_credit *= lot_size

        day_path = []
        incomplete = False
        for d in cycle_days[1:]:
            is_expiry = d == expiry_date
            day_rows = [r for r in _rows_for(d, symbol) if r.expiry == expiry_date]
            if not day_rows:
                continue
            final_price = next((r.underlying_price for r in day_rows if r.underlying_price), None)
            day_by_key = {(r.strike, r.option_type): r for r in day_rows}

            prices = {}
            for leg, strike in strikes.items():
                option_type = LEG_SIDES[leg][0]
                if is_expiry:
                    if final_price is None:
                        break
                    prices[leg] = (
                        max(final_price - strike, 0.0)
                        if option_type == "CE"
                        else max(strike - final_price, 0.0)
                    )
                else:
                    row = day_by_key.get((strike, option_type))
                    if row is None:
                        break
                    prices[leg] = row.settle
            else:
                day_path.append(
                    DayMark(day=d, is_expiry=is_expiry, mark_pnl=_mark_pnl(entry_premiums, prices, lot_size), prices=prices)
                )
                continue
            # a leg's price was missing that day - skip the day silently,
            # but on the expiry day itself that means we can't close the
            # books on this cycle at all.
            if is_expiry:
                incomplete = True
        if incomplete or not day_path or not day_path[-1].is_expiry:
            continue

        paths.append(
            CyclePath(
                symbol=symbol,
                entry_date=entry_date,
                expiry_date=expiry_date,
                spot_entry=spot,
                lot_size=lot_size,
                strikes=strikes,
                entry_premiums=entry_premiums,
                entry_cost=entry_cost,
                net_credit=net_credit,
                path=day_path,
            )
        )

    return paths


def apply_stop_loss(cycle_paths: list[CyclePath], stop_loss_mult: float | None) -> list[CycleResult]:
    """Resolve each cycle's actual exit: the first day its running loss
    crosses `stop_loss_mult * net_credit`, or expiry if it never does
    (or `stop_loss_mult` is None).
    """
    results = []
    for cp in cycle_paths:
        threshold = -stop_loss_mult * cp.net_credit if stop_loss_mult is not None else None
        exit_mark = cp.path[-1]
        stopped_out = False
        if threshold is not None:
            for mark in cp.path:
                if not mark.is_expiry and mark.mark_pnl <= threshold:
                    exit_mark = mark
                    stopped_out = True
                    break

        exit_cost = _exit_cost(exit_mark.prices, cp.lot_size, is_expiry=exit_mark.is_expiry)
        pnl = exit_mark.mark_pnl - cp.entry_cost - exit_cost

        results.append(
            CycleResult(
                symbol=cp.symbol,
                entry_date=cp.entry_date,
                expiry_date=cp.expiry_date,
                exit_date=exit_mark.day,
                stopped_out=stopped_out,
                spot_entry=cp.spot_entry,
                lot_size=cp.lot_size,
                strikes=cp.strikes,
                net_credit=cp.net_credit,
                costs=cp.entry_cost + exit_cost,
                pnl=pnl,
            )
        )
    return results


def run_condor_backtest(
    symbol: str,
    start: date,
    end: date,
    k_short: float = 1.0,
    k_wing: float = 1.0,
    atr_window: int = 14,
    stop_loss_mult: float | None = None,
) -> list[CycleResult]:
    paths = build_cycle_paths(symbol, start, end, k_short, k_wing, atr_window)
    return apply_stop_loss(paths, stop_loss_mult)


@dataclass
class RollEvent:
    day: date
    side: str  # "call" or "put"
    old_strikes: tuple[float, float]
    new_strikes: tuple[float, float]
    roll_pnl: float  # realized P&L from closing the old pair, net of both legs' costs


@dataclass
class AdjustedCycleResult:
    symbol: str
    entry_date: date
    expiry_date: date
    spot_entry: float
    lot_size: int
    initial_strikes: dict[str, float]
    net_credit: float
    costs: float
    pnl: float
    rolls: list[RollEvent] = field(default_factory=list)

    @property
    def n_rolls(self) -> int:
        return len(self.rolls)


def run_condor_with_rolls(
    symbol: str,
    start: date,
    end: date,
    k_short: float = 1.0,
    k_wing: float = 1.0,
    atr_window: int = 14,
) -> list[AdjustedCycleResult]:
    """Same condor, held to expiry, but defended: whenever spot actually
    crosses a short strike (that side is "tested"), close that side's
    short+hedge pair and re-open it further out at the same expiry, using
    the day's own chain and a freshly recomputed vol-scaled distance. The
    other (untested) side is left alone. No cap on how many times a side
    can re-roll within one cycle - rolls are cheap to simulate and the
    data should say whether repeated rolling helps or just bleeds costs.
    """
    instrument_key = _underlying_instrument_key(symbol)
    if instrument_key is None:
        raise ValueError(f"no instrument_key found for {symbol!r}")

    rows_by_day = _daily_bhavcopy_range(start, end)
    cycles = _detect_cycles(symbol, rows_by_day)
    vol_index = DailyIndex(read_cached(instrument_key, "days", "1"))
    trading_days = sorted(rows_by_day)

    results = []
    for entry_date, expiry_date in cycles:
        entry_rows = [r for r in _rows_for(entry_date, symbol) if r.expiry == expiry_date]
        if not entry_rows:
            continue

        spot0 = next((r.underlying_price for r in entry_rows if r.underlying_price), None)
        lot_size = next((r.lot_size for r in entry_rows if r.lot_size), None)
        atr0 = vol_index.atr_pct(entry_date.isoformat(), window=atr_window)
        cycle_days = [d for d in trading_days if entry_date <= d <= expiry_date]
        if spot0 is None or lot_size is None or atr0 is None or len(cycle_days) < 2:
            continue

        call_strikes0 = sorted({r.strike for r in entry_rows if r.option_type == "CE"})
        put_strikes0 = sorted({r.strike for r in entry_rows if r.option_type == "PE"})
        if not call_strikes0 or not put_strikes0:
            continue

        move0 = expected_move_pct(atr0, len(cycle_days) - 1)
        initial_strikes = condor_strikes(spot0, call_strikes0, put_strikes0, move0, k_short, k_wing)

        entry_by_key0 = {(r.strike, r.option_type): r for r in entry_rows}
        sides, total_cost, missing = {}, 0.0, False
        for side, short_leg, hedge_leg in (("call", "short_call", "hedge_call"), ("put", "short_put", "hedge_put")):
            short_row = entry_by_key0.get((initial_strikes[short_leg], LEG_SIDES[short_leg][0]))
            hedge_row = entry_by_key0.get((initial_strikes[hedge_leg], LEG_SIDES[hedge_leg][0]))
            if short_row is None or hedge_row is None:
                missing = True
                break
            total_cost += sell_transaction_cost(short_row.settle * lot_size)
            total_cost += buy_transaction_cost(hedge_row.settle * lot_size)
            sides[side] = {
                "strike_short": initial_strikes[short_leg],
                "strike_hedge": initial_strikes[hedge_leg],
                "premium_short": short_row.settle,
                "premium_hedge": hedge_row.settle,
                "banked_pnl": 0.0,  # realized price P&L from prior rolls on this side; costs live in total_cost
            }
        if missing:
            continue

        net_credit = sum(s["premium_short"] - s["premium_hedge"] for s in sides.values()) * lot_size
        rolls: list[RollEvent] = []
        settled = False

        for d in cycle_days[1:]:
            is_expiry = d == expiry_date
            day_rows = [r for r in _rows_for(d, symbol) if r.expiry == expiry_date]
            if not day_rows:
                continue
            spot = next((r.underlying_price for r in day_rows if r.underlying_price), None)
            if spot is None:
                continue

            if is_expiry:
                for side, s in sides.items():
                    option_type = "CE" if side == "call" else "PE"
                    if option_type == "CE":
                        intrinsic_short = max(spot - s["strike_short"], 0.0)
                        intrinsic_hedge = max(spot - s["strike_hedge"], 0.0)
                    else:
                        intrinsic_short = max(s["strike_short"] - spot, 0.0)
                        intrinsic_hedge = max(s["strike_hedge"] - spot, 0.0)
                    s["banked_pnl"] += (s["premium_short"] - intrinsic_short) * lot_size
                    s["banked_pnl"] += (intrinsic_hedge - s["premium_hedge"]) * lot_size
                    total_cost += exercise_cost(intrinsic_hedge * lot_size)
                settled = True
                break

            day_by_key = {(r.strike, r.option_type): r for r in day_rows}
            call_strikes_today = sorted({r.strike for r in day_rows if r.option_type == "CE"})
            put_strikes_today = sorted({r.strike for r in day_rows if r.option_type == "PE"})
            remaining_days = len([x for x in cycle_days if x >= d])
            atr_today = vol_index.atr_pct(d.isoformat(), window=atr_window)

            for side, s in sides.items():
                option_type = "CE" if side == "call" else "PE"
                breached = spot >= s["strike_short"] if option_type == "CE" else spot <= s["strike_short"]
                if not breached or atr_today is None or remaining_days < 2:
                    continue

                move_today = expected_move_pct(atr_today, remaining_days - 1)
                new_pair = condor_strikes(spot, call_strikes_today, put_strikes_today, move_today, k_short, k_wing)
                new_short = new_pair["short_call"] if option_type == "CE" else new_pair["short_put"]
                new_hedge = new_pair["hedge_call"] if option_type == "CE" else new_pair["hedge_put"]
                further = new_short > s["strike_short"] if option_type == "CE" else new_short < s["strike_short"]
                if not further:
                    continue

                old_short_row = day_by_key.get((s["strike_short"], option_type))
                old_hedge_row = day_by_key.get((s["strike_hedge"], option_type))
                new_short_row = day_by_key.get((new_short, option_type))
                new_hedge_row = day_by_key.get((new_hedge, option_type))
                if None in (old_short_row, old_hedge_row, new_short_row, new_hedge_row):
                    continue

                close_pnl = (s["premium_short"] - old_short_row.settle) * lot_size
                close_pnl += (old_hedge_row.settle - s["premium_hedge"]) * lot_size
                close_cost = buy_transaction_cost(old_short_row.settle * lot_size)
                close_cost += sell_transaction_cost(old_hedge_row.settle * lot_size)
                open_cost = sell_transaction_cost(new_short_row.settle * lot_size)
                open_cost += buy_transaction_cost(new_hedge_row.settle * lot_size)

                s["banked_pnl"] += close_pnl
                total_cost += close_cost + open_cost
                rolls.append(
                    RollEvent(
                        day=d,
                        side=side,
                        old_strikes=(s["strike_short"], s["strike_hedge"]),
                        new_strikes=(new_short, new_hedge),
                        roll_pnl=close_pnl - close_cost - open_cost,
                    )
                )
                s["strike_short"], s["strike_hedge"] = new_short, new_hedge
                s["premium_short"], s["premium_hedge"] = new_short_row.settle, new_hedge_row.settle

        if not settled:
            continue

        total_pnl = sum(s["banked_pnl"] for s in sides.values()) - total_cost
        results.append(
            AdjustedCycleResult(
                symbol=symbol,
                entry_date=entry_date,
                expiry_date=expiry_date,
                spot_entry=spot0,
                lot_size=lot_size,
                initial_strikes=initial_strikes,
                net_credit=net_credit,
                costs=total_cost,
                pnl=total_pnl,
                rolls=rolls,
            )
        )

    return results
