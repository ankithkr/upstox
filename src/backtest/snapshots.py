"""Per-day strategy snapshots - the single source of truth for backtest and UI.

For every trading day this walks the whole top-down funnel and keeps the
result of each step, so the same pass produces both the list of trades
(`taken_trades`) and the sector -> stock heatmap the review UI shows:

  1. market regime gate  (NIFTY 09:30 move picks the side; India VIX and
     the NIFTY 20-day trend must allow it)
  2. sectors             (strongest `top_sectors` in the trade direction)
  3. stocks              (momentum band, opening volume, no duplicates)
  4. ORB simulation      (30-minute range breakout, ATR-floored stop)
  5. breakout-volume filter, then the first `max_trades_per_day` entries

Nothing here looks at data from after the moment a decision is made,
except the intraday simulation itself, which walks candles forward.
"""

from src.backtest.costs import net_r_multiple, round_trip_cost_pct
from src.backtest.history import History
from src.backtest.orb_engine import LONG, SHORT, simulate_trade
from src.calculations.percentage import pct_change
from src.data.stocks import INDEX_CONSTITUENTS
from src.data.universe import V2_SECTORS
from src.strategy.filters import classify_stock_momentum
from src.strategy.params import DEFAULT_PARAMS, StrategyParams

BULLISH, BEARISH, NEUTRAL = "BULLISH", "BEARISH", "NEUTRAL"
NO_TRADE = "NO_TRADE"


def evaluate_gate(direction, vix, nifty_trend_pct, params: StrategyParams) -> tuple[bool, list[str]]:
    """Is the market regime tradeable? Returns (ok, reasons it is not)."""
    if direction is None:
        return False, [f"NIFTY 09:30 move within ±{params.nifty_band_pct}% - no side"]
    reasons = []
    if vix is None:
        reasons.append("no India VIX reading")
    elif vix >= params.max_vix:
        reasons.append(f"VIX {vix:.1f} ≥ {params.max_vix:g}")
    sign = 1 if direction == LONG else -1
    if nifty_trend_pct is None:
        reasons.append("no NIFTY 20-day trend")
    elif sign * nifty_trend_pct <= params.min_nifty_trend_pct:
        want = "uptrend" if direction == LONG else "downtrend"
        reasons.append(f"NIFTY 20-day trend {nifty_trend_pct:+.1f}% - no {want} to trade with")
    return not reasons, reasons


def _r(value, digits=2):
    return None if value is None else round(value, digits)


def _stock_snapshots(h: History, day: str) -> dict:
    snaps = {}
    for symbol, days in h.stock_5m.items():
        candles = days.get(day)
        if not candles or len(candles) < 4:
            continue
        prev = h.stock_daily[symbol].prev_close(day)
        if prev is None:
            continue
        snaps[symbol] = (pct_change(candles[2][4], prev), candles)
    return snaps


def compute_day_snapshots(
    h: History, params: StrategyParams = DEFAULT_PARAMS, start: str | None = None, end: str | None = None
) -> list[dict]:
    cost_pct = round_trip_cost_pct(params.cost_notional, params.brokerage_per_order, params.slippage_pct)
    out = []

    for day in h.days:
        if (start and day < start) or (end and day > end):
            continue
        nifty_candles = h.nifty_15m[day]
        nifty_prev = h.nifty_daily.prev_close(day)
        if not nifty_candles or nifty_prev is None:
            continue

        nifty_change = pct_change(nifty_candles[0][4], nifty_prev)
        direction = None
        if abs(nifty_change) > params.nifty_band_pct:
            direction = LONG if nifty_change > 0 else SHORT
        sign = 1 if direction == LONG else -1
        vix = h.vix_daily.prev_close(day)
        nifty_trend = h.nifty_daily.trend_pct(day)
        gate_ok, gate_reasons = evaluate_gate(direction, vix, nifty_trend, params)
        bias = NEUTRAL if direction is None else (BULLISH if direction == LONG else BEARISH)

        snaps = _stock_snapshots(h, day)
        breadth = round(100 * sum(1 for c, _ in snaps.values() if c > 0) / len(snaps), 1) if snaps else None

        sector_changes = {}
        for name in V2_SECTORS:
            candles = h.sector_15m[name].get(day)
            prev = h.sector_daily[name].prev_close(day)
            if candles and prev is not None:
                sector_changes[name] = pct_change(candles[0][4], prev)

        selected = []
        if gate_ok:
            eligible = [n for n, c in sector_changes.items() if sign * c > params.sector_band_pct]
            selected = sorted(eligible, key=lambda n: sign * sector_changes[n], reverse=True)[: params.top_sectors]

        sector_rows = {}
        for name, change in sector_changes.items():
            stocks = []
            for symbol in INDEX_CONSTITUENTS.get(name, []):
                if symbol not in snaps:
                    continue
                stock_change, _ = snaps[symbol]
                stocks.append(
                    {
                        "symbol": symbol,
                        "change": round(stock_change, 2),
                        "momentum": classify_stock_momentum(stock_change),
                        "direction_match": (sign * stock_change > 0) if direction else None,
                        "open_vol_ratio": _r(h.stock_volume[symbol].opening_ratio(day)),
                        "qualifies": False,
                        "note": None,
                        "trade": None,
                        "taken": False,
                    }
                )
            if abs(change) <= params.sector_band_pct:
                classification = NO_TRADE
            else:
                classification = BULLISH if change > 0 else BEARISH
            sector_rows[name] = {
                "name": name,
                "change": round(change, 2),
                "classification": classification,
                "selected": name in selected,
                "has_constituents": bool(INDEX_CONSTITUENTS.get(name)),
                "stocks": stocks,
            }

        candidates = _evaluate_selected(
            h, day, params, selected, sector_rows, snaps, sign, direction,
            bias, nifty_trend, vix, cost_pct, sector_changes,
        )
        candidates.sort(key=lambda row: row["trade"]["entry_time"])
        for i, row in enumerate(candidates):
            if i < params.max_trades_per_day:
                row["taken"] = True
            else:
                row["note"] = f"skipped: already {params.max_trades_per_day} trades today"

        out.append(
            {
                "date": day,
                "nifty_change": round(nifty_change, 2),
                "nifty_trend": _r(nifty_trend),
                "vix": _r(vix),
                "breadth": breadth,
                "market_bias": bias,
                "direction": direction,
                "gate_ok": gate_ok,
                "gate_reasons": gate_reasons,
                "trades_taken": sum(1 for r in candidates if r["taken"]),
                "sectors": [sector_rows[n] for n in V2_SECTORS if n in sector_rows],
            }
        )
    return out


def _evaluate_selected(h, day, params, selected, sector_rows, snaps, sign, direction, bias,
                       nifty_trend, vix, cost_pct, sector_changes) -> list[dict]:
    """Run the stock filters + simulation for the selected sectors; return rows holding a tradeable trade."""
    seen, tradeable = set(), []
    for name in selected:
        sector_change = sector_changes[name]
        for row in sector_rows[name]["stocks"]:
            symbol = row["symbol"]
            stock_change, candles = snaps[symbol]
            if sign * stock_change <= 0:
                row["note"] = "moving against the trade direction"
                continue
            if sign * stock_change < params.stock_min_move_pct or abs(stock_change) > params.stock_max_move_pct:
                row["note"] = "move outside the allowed band"
                continue
            if symbol in seen:
                row["note"] = "already considered under a stronger sector"
                continue
            seen.add(symbol)
            ratio = row["open_vol_ratio"]
            if ratio is None or ratio < params.min_opening_volume_ratio:
                shown = f"{ratio:g}" if ratio is not None else "n/a"
                row["note"] = f"opening volume {shown}× normal, needs {params.min_opening_volume_ratio:g}×"
                continue

            row["qualifies"] = True
            n_or = params.opening_range_candles
            atr = h.stock_daily[symbol].atr_pct(day)
            trade = simulate_trade(
                direction,
                max(c[2] for c in candles[:n_or]),
                min(c[3] for c in candles[:n_or]),
                candles[n_or:],
                breakeven_rrr=params.breakeven_rrr,
                target_rrr=params.target_rrr,
                stop_floor_pct=params.stop_floor_atr * (atr or 0),
            )
            if trade is None:
                row["note"] = "qualified, but no breakout entry triggered"
                continue

            breakout_ratio = h.stock_volume[symbol].slot_ratio(day, trade["breakout_time"])
            row["trade"] = {
                **trade,
                "date": day,
                "sector": name,
                "symbol": symbol,
                "market_bias": bias,
                "sector_change": round(sector_change, 2),
                "stock_change": round(stock_change, 2),
                "open_vol_ratio": ratio,
                "breakout_vol_ratio": _r(breakout_ratio),
                "atr_pct": _r(atr),
                "vix": _r(vix),
                "nifty_trend": _r(nifty_trend),
                "cost_pct": round(cost_pct, 3),
                "net_r": round(net_r_multiple(trade["r_multiple"], trade["risk_pct"], cost_pct), 3),
            }
            if breakout_ratio is None or breakout_ratio < params.min_breakout_volume_ratio:
                shown = f"{breakout_ratio:.1f}" if breakout_ratio is not None else "n/a"
                row["note"] = f"skipped: breakout volume {shown}× normal, needs {params.min_breakout_volume_ratio:g}×"
                continue
            tradeable.append(row)
    return tradeable


def taken_trades(days: list[dict]) -> list[dict]:
    trades = [row["trade"] for d in days for s in d["sectors"] for row in s["stocks"] if row["taken"]]
    trades.sort(key=lambda t: (t["date"], t["entry_time"]))
    return trades
