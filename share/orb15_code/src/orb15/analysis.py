"""Trade collection, sizing and summary statistics for the ORB-15 study."""
import math
import random
import statistics as st
from dataclasses import dataclass
from typing import Optional

from src.orb15.costs import round_trip_charges
from src.orb15.data import OPEN_MIN, complete_days
from src.orb15.engine import ExitRule, Trade, run_day

CAPITAL = 100_000.0
LEVERAGE = 5.0                         # assumed MIS buying power
NOTIONAL = CAPITAL * LEVERAGE / 5      # each of the 5 stocks gets an equal slice: Rs 1,00,000 per position


@dataclass
class Rec:
    """One trade plus the context known at entry time (no look-ahead)."""
    symbol: str
    day: str
    t: Trade
    hi: float
    lo: float
    width_pct: float          # opening-range width as % of range low
    gap_pct: float            # today's open vs previous close
    rel_width: Optional[float]  # range width / mean daily range of last 5-10 days
    c1_dir: int               # +1/-1: direction of the 09:15-09:30 candle
    trend_dir: int            # +1/-1: 10:00 price vs 09:15 open
    entry_min: int            # minute-of-day of the entry candle
    entry_vol_ratio: Optional[float]  # entry-candle volume / mean 1-min volume 09:30-10:00
    dow: int
    month: str
    # filled by size()
    qty: int = 0
    charges: float = 0.0
    net_rs: float = 0.0
    gross_rs: float = 0.0
    notional: float = 0.0

    @property
    def aligned_gap(self):
        return (self.gap_pct > 0) == (self.t.side == "LONG")

    @property
    def aligned_c1(self):
        return (self.c1_dir > 0) == (self.t.side == "LONG")

    @property
    def aligned_trend(self):
        return (self.trend_dir > 0) == (self.t.side == "LONG")


def size(rec: Rec, notional: float = NOTIONAL) -> Rec:
    """Fixed-notional sizing so every exit rule is compared on the same capital."""
    t = rec.t
    qty = max(int(notional // t.entry), 0)
    rec.qty = qty
    rec.gross_rs = qty * t.pnl
    rec.charges = round_trip_charges(t.side, qty, t.entry, t.exit) if qty else 0.0
    rec.net_rs = rec.gross_rs - rec.charges
    rec.notional = qty * t.entry
    return rec


def _daily_context(daily: dict):
    dates = sorted(daily)
    return dates, {d: i for i, d in enumerate(dates)}


def collect(data, symbols, rule: ExitRule, **kw) -> list[Rec]:
    """Run the strategy for every complete day of every symbol."""
    recs = []
    for sym in symbols:
        days, daily = data[sym]
        dates, pos = _daily_context(daily)
        for day in complete_days(days):
            cs = days[day]
            (hi, lo, _), trades = run_day(cs, rule, **kw)
            if not trades:
                continue
            i = pos.get(day)
            prev_close = daily[dates[i - 1]][3] if i else cs[0][1]
            prior = [daily[d] for d in dates[max(0, i - 10):i]] if i else []
            rel = None
            if len(prior) >= 5:
                avg_rng = st.mean((d[1] - d[2]) for d in prior)
                rel = (hi - lo) / avg_rng if avg_rng else None
            seg = cs[15:45]
            mean_vol = st.mean(c[5] for c in seg)
            for t in trades:
                ec = cs[t.entry_idx]
                recs.append(size(Rec(
                    symbol=sym, day=day, t=t, hi=hi, lo=lo,
                    width_pct=(hi - lo) / lo * 100,
                    gap_pct=(cs[0][1] / prev_close - 1) * 100,
                    rel_width=rel,
                    c1_dir=1 if cs[14][4] >= cs[0][1] else -1,
                    trend_dir=1 if cs[44][4] >= cs[0][1] else -1,
                    entry_min=ec[0],
                    entry_vol_ratio=ec[5] / mean_vol if mean_vol else None,
                    dow=_dow(day), month=day[:7],
                )))
    return recs


def _dow(day: str) -> int:
    from datetime import date
    return date.fromisoformat(day).weekday()


# ----------------------------------------------------------------- statistics

def max_drawdown(series):
    peak, dd = 0.0, 0.0
    cum = 0.0
    for x in series:
        cum += x
        peak = max(peak, cum)
        dd = min(dd, cum - peak)
    return dd


def summarize(recs: list[Rec]) -> dict:
    """Headline numbers at fixed Rs 1L notional per trade; *_net figures are after charges."""
    if not recs:
        return {"n": 0}
    net = [r.net_rs for r in recs]
    gross = [r.gross_rs for r in recs]
    netR = [r.net_rs / (r.qty * r.t.risk) if r.qty else 0.0 for r in recs]
    wins = [x for x in net if x > 0]
    losses = [x for x in net if x <= 0]
    n = len(recs)
    bps = [r.net_rs / r.notional * 1e4 for r in recs]
    sd = st.pstdev(bps) if n > 1 else 0.0
    ordered = sorted(recs, key=lambda r: (r.day, r.t.entry_idx))
    return {
        "n": n,
        "win_pct": 100 * len(wins) / n,
        "avg_R_gross": st.mean(r.t.r for r in recs),
        "avg_net_bps": st.mean(r.net_rs / r.notional * 1e4 for r in recs if r.notional),
        "avg_gross_bps": st.mean(r.gross_rs / r.notional * 1e4 for r in recs if r.notional),
        "avg_charge_bps": st.mean(r.charges / r.notional * 1e4 for r in recs if r.notional),
        "avg_R_net": st.mean(netR),
        "avg_ret_pct": st.mean(r.t.pnl / r.t.entry * 100 for r in recs),
        "net_rs": sum(net),
        "gross_rs": sum(gross),
        "charges": sum(r.charges for r in recs),
        "pf": (sum(wins) / -sum(losses)) if losses and sum(losses) < 0 else float("inf"),
        "t_stat": (st.mean(bps) / (sd / math.sqrt(n))) if sd else 0.0,
        "max_dd_rs": max_drawdown([r.net_rs for r in ordered]),
        "avg_win_R": st.mean(r.t.r for r in recs if r.net_rs > 0) if wins else 0.0,
        "avg_loss_R": st.mean(r.t.r for r in recs if r.net_rs <= 0) if losses else 0.0,
        "avg_risk_pct": st.mean(r.t.risk / r.t.entry * 100 for r in recs),
        "avg_notional": st.mean(r.notional for r in recs),
        "same_bar_pct": 100 * sum(r.t.same_bar for r in recs) / n,
    }


def bootstrap_ci(values, iters=4000, seed=7):
    """95% CI of the mean via a plain bootstrap (trades treated as independent)."""
    rnd = random.Random(seed)
    n = len(values)
    means = sorted(st.mean(rnd.choices(values, k=n)) for _ in range(iters))
    return means[int(0.025 * iters)], means[int(0.975 * iters)]


def day_pnl(recs: list[Rec]) -> dict:
    out = {}
    for r in recs:
        out[r.day] = out.get(r.day, 0.0) + r.net_rs
    return dict(sorted(out.items()))
