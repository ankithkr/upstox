"""Forward-test (paper trading) engine for the top-down ORB strategy.

Same rules as src.backtest (NIFTY bias -> top sectors -> stock filter ->
15-min range -> 5-min breakout -> entry / SL / 1:2 target / breakeven at
1:1 / 3:15 exit), but built to run candle-by-candle against a live feed
and to size real positions from a capital base.

The engine is stateless: `run_day` recomputes the whole day from the
candles that have *closed* by `now`, so a restart mid-day, or a late
candle, can't corrupt anything - the next tick just recomputes. Orders
are modelled as resting stop-entry / stop-loss / target orders, checked
against closed 5-min candles.
"""

import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from src.backtest.orb_engine import (
    BREAKEVEN_RRR,
    EOD_EXIT,
    LONG,
    SHORT,
    SL_BUFFER_PCT,
    STOPPED_BREAKEVEN,
    STOPPED_LOSS,
    TARGET_HIT,
    TARGET_RRR,
)
from src.calculations.percentage import pct_change
from src.data.indices import (
    NIFTY_50_INSTRUMENT_KEY,
    SECTOR_INDEX_INSTRUMENT_KEYS,
    SECTOR_INDICES,
)
from src.data.stocks import INDEX_CONSTITUENTS
from src.paper import config
from src.paper.charges import round_trip_charges
from src.strategy.filters import IDEAL_MOMENTUM, classify_stock_momentum
from src.strategy.market_bias import BULLISH, NEUTRAL, get_market_bias
from src.strategy.sector_selection import DEFAULT_TOP_N, select_sectors

OPENING_CANDLES = 3  # 09:15-09:30 in 5-min candles
SELECTION_GRACE_MINUTES = 10  # give up waiting for missing stock candles after 09:40

# Trade / plan states.
WATCHING, PENDING, OPEN, CLOSED, EXPIRED, DEAD = "WATCHING", "PENDING", "OPEN", "CLOSED", "EXPIRED", "DEAD"
SKIPPED = "SKIPPED"

TRADE_COLUMNS = [
    "trade_id", "date", "sector", "symbol", "direction", "market_bias",
    "sector_change", "stock_change", "opening_high", "opening_low",
    "breakout_time", "entry_time", "entry_price", "stop_loss", "target",
    "qty", "position_value", "risk_amount", "status", "outcome",
    "exit_time", "exit_price", "last_price", "gross_pnl", "charges",
    "net_pnl", "r_multiple", "hold_minutes", "note",
]  # fmt: skip


@dataclass(frozen=True)
class ExecutionRules:
    slippage_pct: float = config.SLIPPAGE_PCT
    # A candle that opens beyond a resting order's level fills at the open,
    # not the level (gaps). The backtest ignores this; keep it on for paper.
    gap_fills: bool = True
    force_exit_candle_start: str = config.FORCE_EXIT_CANDLE_START
    last_entry_candle_start: str = config.LAST_ENTRY_CANDLE_START


@dataclass
class Setup:
    symbol: str
    key: str
    sector: str
    direction: str
    opening_high: float
    opening_low: float
    stock_change: float
    sector_change: float
    order: int


@dataclass
class DaySelection:
    day: str
    market_bias: str
    nifty_change: float
    direction: str | None
    sector_changes: dict
    sectors: list
    setups: list
    complete: bool = True


@dataclass
class Plan:
    """One setup's journey through the day, independent of position size."""

    setup: Setup
    state: str = WATCHING
    breakout_time: str | None = None
    entry_ts: str | None = None  # start of the candle the entry filled in
    entry_price: float | None = None
    stop_loss: float | None = None
    target: float | None = None
    outcome: str | None = None
    exit_ts: str | None = None  # start of the candle the exit happened in
    exit_time: str | None = None  # when it's shown (EOD exits show the candle end)
    exit_price: float | None = None
    last_price: float | None = None


@dataclass
class DayResult:
    day: str
    selection: DaySelection | None
    trades: list = field(default_factory=list)
    pending: list = field(default_factory=list)
    watching: list = field(default_factory=list)


def closed(candles: list[tuple], minutes: int, now: datetime) -> list[tuple]:
    """Candles whose full interval has elapsed by `now`."""
    delta = timedelta(minutes=minutes)
    return [c for c in candles if datetime.fromisoformat(c[0]) + delta <= now]


def _hhmm(ts: str) -> str:
    return ts[11:16]


def _minutes_between(start_ts: str, end_ts: str) -> int:
    return round((datetime.fromisoformat(end_ts) - datetime.fromisoformat(start_ts)).total_seconds() / 60)


def _offset(direction, price, amount):
    return price + amount if direction == LONG else price - amount


# --- selection (the 09:30 top-down filter) -----------------------------------


def select_day(day: str, feed, now: datetime, sector_top_n: int = DEFAULT_TOP_N) -> DaySelection | None:
    """Market bias -> sectors -> qualifying stocks, from the first 15 minutes.

    Returns None until the 09:15-09:30 candle has closed. `complete` is
    False if some qualifying-sector stock has no data yet (feed lag), so
    the caller retries instead of caching a partial watchlist.
    """
    nifty = closed(feed.candles(NIFTY_50_INSTRUMENT_KEY, "minutes", "15", day), 15, now)
    if not nifty:
        return None
    nifty_prev = feed.prev_close(NIFTY_50_INSTRUMENT_KEY, day)
    if nifty_prev is None:
        return None
    nifty_change = pct_change(nifty[0][4], nifty_prev)
    bias = get_market_bias(nifty_change)

    def sector_change(name):
        key = SECTOR_INDEX_INSTRUMENT_KEYS[name]
        c15 = closed(feed.candles(key, "minutes", "15", day), 15, now)
        prev = feed.prev_close(key, day)
        return (name, pct_change(c15[0][4], prev)) if c15 and prev is not None else None

    with ThreadPoolExecutor(max_workers=8) as pool:
        sector_changes = dict(r for r in pool.map(sector_change, SECTOR_INDICES) if r)

    sectors = select_sectors(sector_changes, bias)
    direction = None if bias == NEUTRAL else (LONG if bias == BULLISH else SHORT)
    selection = DaySelection(day, bias, nifty_change, direction, sector_changes, sectors, [])
    if not sectors:
        return selection

    seen, wanted = set(), []
    for sector in sectors:
        for symbol in INDEX_CONSTITUENTS.get(sector, []):
            # A stock in two selected sectors is one position, not two.
            if symbol not in seen:
                seen.add(symbol)
                wanted.append((sector, symbol))

    def load(item):
        sector, symbol = item
        key = feed.symbol_key(symbol)
        if key is None:
            return item, None, None
        return item, key, closed(feed.candles(key, "minutes", "5", day), 5, now)

    with ThreadPoolExecutor(max_workers=8) as pool:
        loaded = list(pool.map(load, wanted))

    for order, ((sector, symbol), key, candles) in enumerate(loaded):
        if key is None:
            continue
        if len(candles) < OPENING_CANDLES:
            selection.complete = False
            continue
        prev = feed.prev_close(key, day)
        if prev is None:
            continue
        change = pct_change(candles[2][4], prev)
        if not (change > 0 if direction == LONG else change < 0):
            continue
        if classify_stock_momentum(change) != IDEAL_MOMENTUM:
            continue
        selection.setups.append(
            Setup(
                symbol=symbol,
                key=key,
                sector=sector,
                direction=direction,
                opening_high=max(c[2] for c in candles[:OPENING_CANDLES]),
                opening_low=min(c[3] for c in candles[:OPENING_CANDLES]),
                stock_change=round(change, 2),
                sector_change=round(sector_changes[sector], 2),
                order=order,
            )
        )

    grace_over = now >= datetime.fromisoformat(f"{day}T09:30:00+05:30") + timedelta(minutes=SELECTION_GRACE_MINUTES)
    if grace_over:
        selection.complete = True
    return selection


# --- per-setup walk (breakout -> entry -> exit) ------------------------------


def walk(setup: Setup, candles: list[tuple], rules: ExecutionRules) -> Plan:
    """Advance one setup through the closed 5-min candles of the day."""
    plan = Plan(setup=setup)
    d = setup.direction
    slip = rules.slippage_pct / 100
    planned_entry = risk = be_trigger = current_stop = None
    at_breakeven = False

    for i in range(OPENING_CANDLES, len(candles)):
        ts, o, h, l, c, _ = candles[i]
        start = _hhmm(ts)

        if plan.state == WATCHING:
            if start >= rules.last_entry_candle_start:
                break
            if (d == LONG and c > setup.opening_high) or (d == SHORT and c < setup.opening_low):
                plan.breakout_time = ts
                planned_entry = h if d == LONG else l
                plan.stop_loss = l * (1 - SL_BUFFER_PCT / 100) if d == LONG else h * (1 + SL_BUFFER_PCT / 100)
                risk = abs(planned_entry - plan.stop_loss)
                if risk <= 0:
                    plan.state = DEAD
                    break
                plan.target = _offset(d, planned_entry, TARGET_RRR * risk)
                be_trigger = _offset(d, planned_entry, BREAKEVEN_RRR * risk)
                plan.state = PENDING
            continue

        if plan.state == PENDING:
            if start >= rules.last_entry_candle_start:
                plan.state = EXPIRED
                break
            triggered = h >= planned_entry if d == LONG else l <= planned_entry
            if not triggered:
                continue
            fill = planned_entry
            if rules.gap_fills:
                fill = max(planned_entry, o) if d == LONG else min(planned_entry, o)
            past_target = fill >= plan.target if d == LONG else fill <= plan.target
            if past_target:  # gapped straight through the target - not a tradeable fill
                plan.state = EXPIRED
                break
            plan.entry_price = fill * (1 + slip) if d == LONG else fill * (1 - slip)
            plan.entry_ts = ts
            current_stop = plan.stop_loss
            plan.state = OPEN
            # fall through: the entry candle itself can already hit stop / target

        if plan.state == OPEN:
            is_entry_candle = ts == plan.entry_ts
            moved_be_now = False
            if not at_breakeven:
                reached = h >= be_trigger if d == LONG else l <= be_trigger
                if reached:
                    current_stop = plan.entry_price
                    at_breakeven = moved_be_now = True

            stopped = l <= current_stop if d == LONG else h >= current_stop
            hit_target = h >= plan.target if d == LONG else l <= plan.target
            gap_ok = rules.gap_fills and not is_entry_candle

            if stopped:
                px = current_stop
                if gap_ok and not moved_be_now:
                    px = min(px, o) if d == LONG else max(px, o)
                px = px * (1 - slip) if d == LONG else px * (1 + slip)
                _close(plan, STOPPED_BREAKEVEN if at_breakeven else STOPPED_LOSS, ts, ts, px)
            elif hit_target:
                px = plan.target
                if gap_ok:
                    px = max(px, o) if d == LONG else min(px, o)
                _close(plan, TARGET_HIT, ts, ts, px)
            elif start >= rules.force_exit_candle_start:
                end = (datetime.fromisoformat(ts) + timedelta(minutes=5)).isoformat()
                px = c * (1 - slip) if d == LONG else c * (1 + slip)
                _close(plan, EOD_EXIT, ts, end, px)
            else:
                plan.last_price = c

            if plan.state == CLOSED:
                break

    return plan


def _close(plan: Plan, outcome: str, exit_ts: str, exit_time: str, price: float):
    plan.state, plan.outcome = CLOSED, outcome
    plan.exit_ts, plan.exit_time, plan.exit_price = exit_ts, exit_time, price


# --- sizing, cash and the trade records --------------------------------------


def build_trades(
    plans: list[Plan],
    selection: DaySelection,
    start_equity: float,
    risk_pct: float = config.RISK_PER_TRADE_PCT,
    leverage: float = config.LEVERAGE,
) -> list[dict]:
    """Turn plans that reached an entry into sized, costed trade records.

    Fills are processed in time order. A position's value is held against
    free cash until the candle *after* it exits, so an exit and a new entry
    inside one candle never reuse the same rupees (conservative).
    """
    risk_amount = start_equity * risk_pct / 100
    buying_power = start_equity * leverage

    filled = sorted(
        (p for p in plans if p.state in (OPEN, CLOSED)), key=lambda p: (p.entry_ts, p.setup.order)
    )
    trades = []
    held: list[tuple[Plan, int]] = []  # (plan, qty) still tying up cash
    realised = 0.0  # net P&L released from positions that exited in earlier candles

    for plan in filled:
        for pos in [x for x in held if x[0].state == CLOSED and x[0].exit_ts < plan.entry_ts]:
            held.remove(pos)
            realised += _net_pnl(*pos)[2]

        risk_per_share = abs(plan.entry_price - plan.stop_loss)
        available = buying_power + realised - sum(q * p.entry_price for p, q in held)
        qty_by_risk = math.floor(risk_amount / risk_per_share) if risk_per_share else 0
        qty_by_cash = math.floor(max(available, 0) / plan.entry_price)
        qty = min(qty_by_risk, qty_by_cash)

        trade = _base_trade(plan, selection)
        if qty < 1:
            trade.update(status=SKIPPED, qty=0, note=_skip_reason(qty_by_risk, qty_by_cash))
            trades.append(trade)
            continue

        note = "cash-limited (qty reduced)" if qty_by_cash < qty_by_risk else ""
        gross, charges, net = _net_pnl(plan, qty)
        trade.update(
            qty=qty,
            position_value=round(qty * plan.entry_price, 2),
            risk_amount=round(qty * risk_per_share, 2),
            status=plan.state,
            gross_pnl=gross,
            charges=charges,
            net_pnl=net,
            r_multiple=round(gross / (qty * risk_per_share), 2),
            note=note,
        )
        held.append((plan, qty))
        trades.append(trade)

    return trades


def _net_pnl(plan: Plan, qty: int) -> tuple[float, float, float]:
    """(gross, charges, net) - closed trades at the exit price, open ones marked to the last close."""
    px = plan.exit_price if plan.state == CLOSED else plan.last_price
    if px is None:
        px = plan.entry_price
    d = plan.setup.direction
    gross = (px - plan.entry_price) * qty if d == LONG else (plan.entry_price - px) * qty
    charges = round_trip_charges(d, qty, plan.entry_price, px)
    return round(gross, 2), charges, round(gross - charges, 2)


def _skip_reason(qty_by_risk: int, qty_by_cash: int) -> str:
    if qty_by_risk < 1:
        return "one share risks more than the per-trade risk budget"
    return "not enough free cash for one share"


def _base_trade(plan: Plan, selection: DaySelection) -> dict:
    s = plan.setup
    trade = dict.fromkeys(TRADE_COLUMNS)
    trade.update(
        trade_id=f"{selection.day}-{s.symbol}-{s.direction}",
        date=selection.day,
        sector=s.sector,
        symbol=s.symbol,
        direction=s.direction,
        market_bias=selection.market_bias,
        sector_change=s.sector_change,
        stock_change=s.stock_change,
        opening_high=round(s.opening_high, 2),
        opening_low=round(s.opening_low, 2),
        breakout_time=_hhmm(plan.breakout_time),
        entry_time=_hhmm(plan.entry_ts),
        entry_price=round(plan.entry_price, 2),
        stop_loss=round(plan.stop_loss, 2),
        target=round(plan.target, 2),
        last_price=round(plan.last_price if plan.last_price is not None else plan.entry_price, 2),
        note="",
    )
    if plan.state == CLOSED:
        trade.update(
            outcome=plan.outcome,
            exit_time=_hhmm(plan.exit_time),
            exit_price=round(plan.exit_price, 2),
            last_price=round(plan.exit_price, 2),
            hold_minutes=_minutes_between(plan.entry_ts, plan.exit_time),
        )
    return trade


# --- one call = one full recompute of the day ---------------------------------


def track_day(
    selection: DaySelection,
    feed,
    now: datetime,
    start_equity: float,
    rules: ExecutionRules = ExecutionRules(),
) -> DayResult:
    """Walk every watchlist stock through the closed candles and size the fills."""
    result = DayResult(day=selection.day, selection=selection)

    def load(setup):
        return setup, closed(feed.candles(setup.key, "minutes", "5", selection.day), 5, now)

    with ThreadPoolExecutor(max_workers=8) as pool:
        loaded = list(pool.map(load, selection.setups))

    plans = [walk(setup, candles, rules) for setup, candles in loaded]
    result.trades = build_trades(plans, selection, start_equity)
    result.pending = [p.setup.symbol for p in plans if p.state == PENDING]
    result.watching = [p.setup.symbol for p in plans if p.state == WATCHING]
    return result


def run_day(
    day: str,
    feed,
    now: datetime,
    start_equity: float,
    rules: ExecutionRules = ExecutionRules(),
    selection: DaySelection | None = None,
) -> DayResult:
    """Everything the engine knows about `day` as of `now`, from scratch."""
    selection = selection or select_day(day, feed, now)
    if selection is None:
        return DayResult(day=day, selection=None)
    return track_day(selection, feed, now, start_equity, rules)
