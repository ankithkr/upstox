"""15-minute-range breakout: range detection, entry detection, trade simulation.

Conventions
-----------
* Candles are 1-minute (minute_of_day, o, h, l, c, v); index 0 is 09:15.
* The opening range is built from 15-minute candles `range_candles` (1-based,
  default (2, 3) = 09:30-10:00). It is known at the END of the last of them,
  so entries are only looked for from that moment on.
* Entry kinds:
    "touch"                    stop-style order at the level; fills the instant
                               any tick trades through it (fill = max(level, open)
                               for longs, i.e. gap-aware).
    "close1"/"close5"/"close15" fires when a 1/5/15-minute candle CLOSES beyond the
                               level; fill at that close.
* Same-candle ambiguity is resolved against the trader: if a candle touches
  both stop and target the stop is assumed hit first.
"""
from dataclasses import dataclass
from typing import Optional

from src.orb15.data import OPEN_MIN

LONG, SHORT = "LONG", "SHORT"


def idx_of(minute_of_day: int) -> int:
    return minute_of_day - OPEN_MIN


def opening_range(candles, range_candles=(2, 3)):
    """-> (high, low, first tradable idx). 15-min candle n covers idx 15(n-1)..15n-1."""
    a, b = range_candles
    seg = candles[15 * (a - 1): 15 * b]
    return max(c[2] for c in seg), min(c[3] for c in seg), 15 * b


@dataclass
class Entry:
    idx: int            # 1-min candle index at which the fill happens
    side: str
    price: float
    level: float        # the range boundary that was broken
    touch: bool         # True: fill happened inside candle `idx` (it can also hit stop/target)
    both: bool = False  # the same 1-min candle also pierced the opposite level


def find_entry(candles, hi, lo, start_idx, last_entry_idx, kind="touch", buffer_pct=0.0,
               sides=(LONG, SHORT), slip_pct=0.0) -> Optional[Entry]:
    """First breakout of `hi` / `lo` at or after start_idx (<= last_entry_idx)."""
    up, dn = hi * (1 + buffer_pct / 100), lo * (1 - buffer_pct / 100)
    n = int(kind[5:]) if kind.startswith("close") else 0
    for i in range(start_idx, min(last_entry_idx, len(candles) - 1) + 1):
        _, o, h, l, c, _ = candles[i]
        if kind == "touch":
            long_hit = LONG in sides and h > up
            short_hit = SHORT in sides and l < dn
            if long_hit and short_hit:
                side = LONG if abs(o - up) <= abs(o - dn) else SHORT
                both = True
            elif long_hit:
                side, both = LONG, False
            elif short_hit:
                side, both = SHORT, False
            else:
                continue
            level = up if side == LONG else dn
            px = max(level, o) if side == LONG else min(level, o)
            px = px * (1 + slip_pct / 100) if side == LONG else px * (1 - slip_pct / 100)
            return Entry(i, side, px, level, True, both)
        # candle-close confirmation on an n-minute bar (bars aligned to 09:15)
        if not ((i + 1) % n == 0 or i == len(candles) - 1):
            continue
        if LONG in sides and c > up:
            return Entry(i, LONG, c * (1 + slip_pct / 100), up, False)
        if SHORT in sides and c < dn:
            return Entry(i, SHORT, c * (1 - slip_pct / 100), dn, False)
    return None


@dataclass
class ExitRule:
    stop: str = "opp"                   # "opp" | "mid" | "frac:<x>" (x * range width) | "pct:<x>" (x % of entry)
    target_r: Optional[float] = None    # take profit at k * risk; None = hold to cutoff
    cutoff: int = 15 * 60 + 15          # minute-of-day: flatten at the OPEN of this candle
    be_after_r: Optional[float] = None  # move stop to entry once +k R reached
    trail_r: Optional[float] = None     # trail stop k*risk behind the best price
    slip_pct: float = 0.0               # adverse slippage applied to stop / cutoff exits


@dataclass
class Trade:
    side: str
    entry_idx: int
    entry: float
    stop: float
    risk: float          # price points between entry and initial stop
    exit_idx: int
    exit: float
    reason: str          # STOP | TARGET | BE | TRAIL | EOD
    mfe: float           # best excursion (points) before exit
    mae: float           # worst adverse excursion (points) before exit
    pnl: float           # gross points per share
    r: float             # pnl / risk
    same_bar: bool       # exited inside the entry candle (path unknowable)
    both_hit: bool = False


def stop_price(rule_stop: str, side: str, entry: float, hi: float, lo: float) -> float:
    width = hi - lo
    if rule_stop == "opp":
        return lo if side == LONG else hi
    if rule_stop == "mid":
        return (hi + lo) / 2
    kind, x = rule_stop.split(":")
    x = float(x)
    dist = x * width if kind == "frac" else entry * x / 100
    return entry - dist if side == LONG else entry + dist


def simulate(candles, e: Entry, hi: float, lo: float, rule: ExitRule) -> Optional[Trade]:
    side, entry = e.side, e.price
    stop = stop_price(rule.stop, side, entry, hi, lo)
    risk = entry - stop if side == LONG else stop - entry
    if risk <= entry * 1e-4:      # entry already through (or touching) the stop - degenerate
        return None
    sgn = 1 if side == LONG else -1
    target = None if rule.target_r is None else entry + sgn * rule.target_r * risk
    cut_idx = min(idx_of(rule.cutoff), len(candles) - 1)
    first = e.idx if e.touch else e.idx + 1
    best = entry
    cur_stop = stop
    mfe = mae = 0.0
    slip = rule.slip_pct / 100

    def fin(i, px, reason):
        pnl = sgn * (px - entry)
        return Trade(side, e.idx, entry, stop, risk, i, px, reason, mfe, mae, pnl, pnl / risk,
                     i == e.idx, e.both)

    for i in range(first, cut_idx + 1):
        _, o, h, l, c, _ = candles[i]
        if i == cut_idx and i > e.idx:
            return fin(i, o * (1 - sgn * slip), "EOD")
        fav, adv = (h, l) if side == LONG else (l, h)
        if (side == LONG and l <= cur_stop) or (side == SHORT and h >= cur_stop):
            gapped = (side == LONG and o < cur_stop) or (side == SHORT and o > cur_stop)
            px = (o if gapped else cur_stop) * (1 - sgn * slip)
            mae = max(mae, sgn * (entry - adv))
            reason = "STOP" if cur_stop == stop else ("BE" if cur_stop == entry else "TRAIL")
            return fin(i, px, reason)
        if target is not None and ((side == LONG and h >= target) or (side == SHORT and l <= target)):
            mfe = max(mfe, sgn * (fav - entry))
            mae = max(mae, sgn * (entry - adv))
            return fin(i, target, "TARGET")
        mfe = max(mfe, sgn * (fav - entry))
        mae = max(mae, sgn * (entry - adv))
        best = max(best, h) if side == LONG else min(best, l)
        if rule.be_after_r is not None and sgn * (best - entry) >= rule.be_after_r * risk:
            cur_stop = max(cur_stop, entry) if side == LONG else min(cur_stop, entry)
        if rule.trail_r is not None:
            t = best - sgn * rule.trail_r * risk
            cur_stop = max(cur_stop, t) if side == LONG else min(cur_stop, t)
    return fin(cut_idx, candles[cut_idx][4], "EOD")


def run_day(candles, rule: ExitRule, range_candles=(2, 3), kind="touch", buffer_pct=0.0,
            last_entry_min=14 * 60 + 30, sides=(LONG, SHORT), max_trades=1, slip_pct=0.0):
    """All trades for one stock-day. A second trade (max_trades=2) is a reversal only."""
    hi, lo, start = opening_range(candles, range_candles)
    last_entry_idx = idx_of(last_entry_min)
    trades, search_from, allowed = [], start, sides
    while len(trades) < max_trades:
        e = find_entry(candles, hi, lo, search_from, last_entry_idx, kind, buffer_pct, allowed, slip_pct)
        if e is None:
            break
        t = simulate(candles, e, hi, lo, rule)
        if t is None:
            break
        trades.append(t)
        if t.reason not in ("STOP", "TRAIL", "BE"):
            break
        allowed = tuple(s for s in sides if s != t.side)
        if not allowed:
            break
        search_from = max(t.exit_idx, e.idx) + 1
    return (hi, lo, start), trades
