"""Multi-year research harness (2023 -> 2026) for the top-down ORB strategy.

Reads only cached candles (run fetch_history.py first). Pure Python.

Pipeline: build per-day features -> generate candidate stock/day setups
-> simulate each with the ORB engine -> apply entry-time filters and the
"max N trades/day" cap -> score net of realistic costs, train vs test.
"""

import os
import statistics
from bisect import bisect_left
from collections import defaultdict
from datetime import date, timedelta

os.environ.setdefault("UPSTOX_OFFLINE", "1")

from precompute_ui import _cached_range
from src.backtest.orb_engine import LONG, SHORT, TARGET_HIT, simulate_trade
from src.calculations.percentage import pct_change
from src.data.indices import NIFTY_50_INSTRUMENT_KEY, SECTOR_INDEX_INSTRUMENT_KEYS
from src.data.stocks import INDEX_CONSTITUENTS
from src.integrations.upstox_history import get_candles
from src.integrations.upstox_instruments import build_equity_symbol_index, load_instrument_master
from src.strategy.filters import classify_sector

DAILY_START, DAILY_END = date(2022, 12, 1), date(2026, 10, 7)
A_START, A_END = date(2023, 1, 2), date(2026, 2, 19)
VIX_KEY = "NSE_INDEX|India VIX"
SECTORS = [
    "NIFTY AUTO", "NIFTY BANK", "NIFTY FINANCIAL SERVICES", "NIFTY FMCG", "NIFTY IT",
    "NIFTY MEDIA", "NIFTY METAL", "NIFTY PHARMA", "NIFTY PSU BANK", "NIFTY REALTY",
    "NIFTY PRIVATE BANK", "NIFTY HEALTHCARE", "NIFTY CONSUMER DURABLES", "NIFTY OIL & GAS",
    "NIFTY FINANCIAL SERVICES EX-BANK", "NIFTY CEMENT",
]
TRAIN_END = "2024-12-31"


# ---------------------------------------------------------------- costs
def cost_pct(notional=50_000, brokerage=12.5, slippage_pct=0.03):
    """Round-trip cost as % of notional: brokerage both legs (+18% GST),
    STT 0.025% on sell, exchange 0.00297%/leg, stamp 0.003% on buy, slippage."""
    b = 2 * brokerage * 1.18 / notional * 100
    return b + 0.025 + 2 * 0.00297 * 1.18 + 0.003 + slippage_pct


# ---------------------------------------------------------------- loading
def _intraday(key, interval, b_range):
    out = []
    if b_range[0] > A_START:
        out += get_candles(key, "minutes", interval, A_START, A_END)
    out += get_candles(key, "minutes", interval, *b_range)
    return out


def _group_by_day(candles):
    g = defaultdict(list)
    for c in candles:
        g[c[0][:10]].append(c)
    return g


def load(max_stocks=None):
    b_range = _cached_range()
    with open("data_cache/research_universe.txt") as f:
        universe = [s for s in f.read().split() if s]
    if max_stocks:
        universe = universe[:max_stocks]
    symbol_key = build_equity_symbol_index(load_instrument_master())

    nifty_15 = _group_by_day(_intraday(NIFTY_50_INSTRUMENT_KEY, "15", b_range))
    nifty_daily = get_candles(NIFTY_50_INSTRUMENT_KEY, "days", "1", DAILY_START, DAILY_END)
    vix_daily = get_candles(VIX_KEY, "days", "1", DAILY_START, DAILY_END)
    sec_15 = {s: _group_by_day(_intraday(SECTOR_INDEX_INSTRUMENT_KEYS[s], "15", b_range)) for s in SECTORS}
    sec_daily = {s: get_candles(SECTOR_INDEX_INSTRUMENT_KEYS[s], "days", "1", DAILY_START, DAILY_END) for s in SECTORS}
    st_5, st_daily = {}, {}
    for sym in universe:
        if sym not in symbol_key:
            continue
        c = _intraday(symbol_key[sym], "5", b_range)
        if not c:
            continue
        st_5[sym] = _group_by_day(c)
        st_daily[sym] = get_candles(symbol_key[sym], "days", "1", DAILY_START, DAILY_END)
    return dict(nifty_15=nifty_15, nifty_daily=nifty_daily, vix=vix_daily, sec_15=sec_15,
                sec_daily=sec_daily, st_5=st_5, st_daily=st_daily)


class DailyIndex:
    """Fast prior-day lookups on a daily candle series."""

    def __init__(self, candles):
        self.c = candles
        self.dates = [x[0][:10] for x in candles]

    def pos(self, day):
        i = bisect_left(self.dates, day)
        return i if i < len(self.dates) and self.dates[i] == day else None

    def prev_close(self, day):
        i = self.pos(day)
        return self.c[i - 1][4] if i else None

    def trend20(self, day):
        """prev close vs mean of the 20 closes up to it, in %."""
        i = self.pos(day)
        if not i or i < 20:
            return None
        closes = [x[4] for x in self.c[i - 20 : i]]
        return 100 * (closes[-1] / (sum(closes) / 20) - 1)

    def atr_pct(self, day, n=14):
        i = self.pos(day)
        if not i or i < n + 1:
            return None
        rows = self.c[i - n : i]
        prevs = self.c[i - n - 1 : i - 1]
        trs = [max(r[2] - r[3], abs(r[2] - p[4]), abs(r[3] - p[4])) for r, p in zip(rows, prevs)]
        return 100 * (sum(trs) / n) / self.c[i - 1][4]


# ---------------------------------------------------------------- candidates
def build_candidates(d, top_sectors=3, nifty_band=0.3, sector_band=0.5):
    """All plausible setups per day (loose), carrying features for later filtering."""
    nd, vd = DailyIndex(d["nifty_daily"]), DailyIndex(d["vix"])
    sd = {s: DailyIndex(c) for s, c in d["sec_daily"].items()}
    std = {s: DailyIndex(c) for s, c in d["st_daily"].items()}

    # per-stock, per-day opening volume (first 3 5-min candles) for relative volume
    open_vol = {s: {day: sum(c[5] for c in cs[:3]) for day, cs in days.items() if len(cs) >= 3}
                for s, days in d["st_5"].items()}
    vol_days = {s: sorted(v) for s, v in open_vol.items()}

    def rel_open_vol(sym, day):
        ds = vol_days[sym]
        i = bisect_left(ds, day)
        prev = ds[max(0, i - 20) : i]
        if len(prev) < 10 or day not in open_vol[sym]:
            return None
        base = sum(open_vol[sym][x] for x in prev) / len(prev)
        return open_vol[sym][day] / base if base else None

    cands, day_info = [], {}
    for day in sorted(d["nifty_15"]):
        n15 = d["nifty_15"][day]
        nprev = nd.prev_close(day)
        if not n15 or nprev is None:
            continue
        n930 = n15[0][4]
        nifty_chg = pct_change(n930, nprev)

        # breadth at 09:30 across the universe
        ups = tot = 0
        snap = {}
        for sym, days in d["st_5"].items():
            cs = days.get(day)
            if not cs or len(cs) < 4:
                continue
            p = std[sym].prev_close(day)
            if p is None:
                continue
            chg = pct_change(cs[2][4], p)
            snap[sym] = (chg, cs, p)
            tot += 1
            ups += chg > 0
        breadth = 100 * ups / tot if tot else None
        vprev = vd.prev_close(day)
        info = dict(nifty_chg=nifty_chg, breadth=breadth, vix=vprev, nifty_trend=nd.trend20(day))
        day_info[day] = info
        if abs(nifty_chg) <= nifty_band:
            continue
        direction = LONG if nifty_chg > 0 else SHORT
        sign = 1 if direction == LONG else -1
        want = "BULLISH" if direction == LONG else "BEARISH"

        secs = {}
        for s in SECTORS:
            c15 = d["sec_15"][s].get(day)
            p = sd[s].prev_close(day)
            if c15 and p is not None:
                ch = pct_change(c15[0][4], p)
                if classify_sector(ch) == want:
                    secs[s] = ch
        ranked = sorted(secs, key=lambda s: sign * secs[s], reverse=True)[:top_sectors]
        seen = set()
        for rank, s in enumerate(ranked):
            for sym in INDEX_CONSTITUENTS.get(s, []):
                if sym not in snap or sym in seen:
                    continue
                chg, cs, p = snap[sym]
                if sign * chg < 0.8 or abs(chg) > 2.5:
                    continue
                seen.add(sym)
                cands.append(dict(
                    date=day, direction=direction, sector=s, symbol=sym, sector_rank=rank + 1,
                    sector_chg=secs[s], stock_chg=chg, rs=sign * (chg - secs[s]),
                    gap=pct_change(cs[0][1], p) * sign,
                    atr_pct=std[sym].atr_pct(day), trend=(std[sym].trend20(day) or 0) * sign,
                    rel_vol=rel_open_vol(sym, day), candles=cs,
                    **{f"m_{k}": v for k, v in info.items()},
                ))
    return cands, day_info


# ---------------------------------------------------------------- simulation
ENGINE_DEFAULTS = dict(max_entry_time=None, max_entry_lag=None, min_stop_pct=0.0, stop_mode="breakout",
                       breakeven_rrr=1.0, trail=False, stop_floor_pct=0.0,
                       entry_mode="breakout", retest_window=6, retest_fill_buffer_pct=0.0)


def simulate(cands, **engine):
    kw = {**ENGINE_DEFAULTS, **engine}
    out = []
    for c in cands:
        cs = c["candles"]
        n_or = kw.get("or_n", 3)
        oh, ol = max(x[2] for x in cs[:n_or]), min(x[3] for x in cs[:n_or])
        kw_c = dict(kw)
        if kw.get("stop_floor_atr"):
            kw_c["stop_floor_pct"] = kw["stop_floor_atr"] * (c["atr_pct"] or 0)
        kw_c.pop("stop_floor_atr", None)
        kw_c.pop("or_n", None)
        t = simulate_trade(c["direction"], oh, ol, cs[n_or:], **kw_c)
        if t is None:
            continue
        t = {**{k: v for k, v in c.items() if k != "candles"}, **t}
        # breakout-candle volume vs the same candle's volume over the last 20 days of this stock
        t["entry_hhmm"] = t["entry_time"][11:16]
        out.append(t)
    return out


def add_breakout_volume(trades, d):
    """rel_bvol = breakout candle volume / mean same-slot volume over prior 20 sessions."""
    slot_vol = {}
    for sym, days in d["st_5"].items():
        sv = defaultdict(dict)
        for day, cs in days.items():
            for c in cs:
                sv[c[0][11:16]][day] = c[5]
        slot_vol[sym] = {k: (sorted(v), v) for k, v in sv.items()}
    for t in trades:
        slot = t["breakout_time"][11:16]
        got = slot_vol[t["symbol"]].get(slot)
        t["rel_bvol"] = None
        if got:
            ds, vals = got
            i = bisect_left(ds, t["date"])
            prev = ds[max(0, i - 20) : i]
            if len(prev) >= 10:
                base = sum(vals[x] for x in prev) / len(prev)
                bc_vol = next((c[5] for c in d["st_5"][t["symbol"]][t["date"]] if c[0] == t["breakout_time"]), None)
                if base and bc_vol is not None:
                    t["rel_bvol"] = bc_vol / base
    return trades


# ---------------------------------------------------------------- scoring
def net_r(t, cpct):
    return t["r_multiple"] - cpct / t["risk_pct"]


def cap_per_day(trades, n):
    """First n entries of each day (entry-time order) - what you could actually take live."""
    by = defaultdict(list)
    for t in trades:
        by[t["date"]].append(t)
    out = []
    for day, ts in by.items():
        ts.sort(key=lambda t: t["entry_time"])
        out += ts[:n]
    return out


def stats(trades, cpct):
    n = len(trades)
    if not n:
        return None
    rs = [net_r(t, cpct) for t in trades]
    wins = sum(1 for t in trades if t["r_multiple"] > 0.05)
    pos, neg = sum(x for x in rs if x > 0), -sum(x for x in rs if x < 0)
    by_day = defaultdict(float)
    for t, r in zip(trades, rs):
        by_day[t["date"]] += r
    eq = peak = dd = 0.0
    for day in sorted(by_day):
        eq += by_day[day]
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    months = defaultdict(float)
    for day, r in by_day.items():
        months[day[:7]] += r
    return dict(n=n, win=100 * wins / n, E=sum(rs) / n, tot=sum(rs), pf=(pos / neg if neg else 9.99),
                dd=dd, pos_months=100 * sum(1 for v in months.values() if v > 0) / len(months),
                months=len(months))


def line(label, s):
    if s is None:
        return f"{label:<44}  (no trades)"
    return (f"{label:<44}{s['n']:>5}{s['win']:>6.1f}{s['E']:>8.3f}{s['tot']:>8.1f}{s['pf']:>6.2f}"
            f"{s['dd']:>7.1f}{s['pos_months']:>6.0f}%")


HEADER = f"{'':<44}{'n':>5}{'win%':>6}{'E[R]net':>8}{'netR':>8}{'PF':>6}{'maxDD':>7}{'+mo':>7}"


def report(label, trades, cpct):
    train = [t for t in trades if t["date"] <= TRAIN_END]
    test = [t for t in trades if t["date"] > TRAIN_END]
    print(line(f"{label} | train", stats(train, cpct)))
    print(line(f"{label} | test", stats(test, cpct)))


def bucket_report(trades, key, cpct, nb=4, edges=None):
    """Quantile buckets (edges from the TRAIN set) with train and test side by side."""
    vals = sorted(key(t) for t in trades if t["date"] <= TRAIN_END and key(t) is not None)
    if len(vals) < nb * 10:
        return
    if edges is None:
        edges = [vals[int(len(vals) * i / nb)] for i in range(1, nb)]
    bounds = [float("-inf")] + list(edges) + [float("inf")]
    for lo, hi in zip(bounds[:-1], bounds[1:]):
        def sel(ts):
            return [t for t in ts if key(t) is not None and lo <= key(t) < hi]
        tr = [t for t in trades if t["date"] <= TRAIN_END]
        te = [t for t in trades if t["date"] > TRAIN_END]
        a, b = stats(sel(tr), cpct), stats(sel(te), cpct)
        fa = f"n={a['n']:4d} win={a['win']:4.1f} E={a['E']:+.3f}" if a else "-"
        fb = f"n={b['n']:4d} win={b['win']:4.1f} E={b['E']:+.3f}" if b else "-"
        print(f"   [{lo:8.2f},{hi:8.2f})  train {fa}   test {fb}")
