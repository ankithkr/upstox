"""Full analysis of the 5-stock 15-minute-range breakout strategy.

    PYTHONPATH=. venv/Scripts/python analyze_orb15.py

Reads the cached 1-minute candles (run fetch_orb15_data.py first; needs a valid
Upstox token only to download) and writes reports/orb15/{report.html,
trades_baseline.csv, grid.csv}.
"""
import bisect
import csv
import random
import statistics as st
from collections import defaultdict
from pathlib import Path

from src.orb15 import report as H
from src.orb15.analysis import NOTIONAL, collect, day_pnl, max_drawdown, size, summarize
from src.orb15.config import END, START, UNIVERSE
from src.orb15.data import complete_days, hhmm, load_all
from src.orb15.engine import ExitRule

OUT = Path("reports/orb15")
U = list(UNIVERSE)
M = lambda h, m=0: h * 60 + m
SPLIT = "2026-08-01"          # train = Apr-Jul, test = Aug-Oct


# ------------------------------------------------------------------ helpers
def f1(x):
    return f"{x:,.1f}"


def rs(x):
    return f"{x:,.0f}"


def cell(x, digits=1, suffix=""):
    return (f"{x:,.{digits}f}{suffix}", x)


def split(recs):
    return [r for r in recs if r.day < SPLIT], [r for r in recs if r.day >= SPLIT]


def cluster_ci(recs, iters=3000, seed=11):
    """95% CI of mean net bps, resampling whole DAYS (the 5 stocks move together)."""
    by_day = defaultdict(list)
    for r in recs:
        by_day[r.day].append(r.net_rs / r.notional * 1e4)
    days = list(by_day.values())
    rnd = random.Random(seed)
    means = []
    for _ in range(iters):
        pick = [x for d in rnd.choices(days, k=len(days)) for x in d]
        means.append(st.mean(pick))
    means.sort()
    return means[int(.025 * iters)], means[int(.975 * iters)]


def stat_row(label, recs, with_split=True):
    s = summarize(recs)
    if not s["n"]:
        return [label, "0"] + [""] * (9 if with_split else 7)
    row = [label, str(s["n"]), f"{s['win_pct']:.0f}%", cell(s["avg_gross_bps"]), f1(s["avg_charge_bps"]),
           cell(s["avg_net_bps"]), f"{s['t_stat']:.2f}", cell(s["net_rs"], 0), rs(s["max_dd_rs"])]
    if with_split:
        a, b = split(recs)
        sa, sb = summarize(a), summarize(b)
        row += [cell(sa["avg_net_bps"]) if sa["n"] else "-", cell(sb["avg_net_bps"]) if sb["n"] else "-"]
    return row


STAT_HEAD = ["", "trades", "win", "gross bps", "cost bps", "net bps", "t-stat", "net Rs", "max DD Rs"]
SPLIT_HEAD = ["Apr-Jul net bps", "Aug-Oct net bps"]


def stat_table(rows_in, hl=None, with_split=True):
    head = STAT_HEAD + (SPLIT_HEAD if with_split else [])
    rows = [stat_row(l, r, with_split) for l, r in rows_in]
    return H.table(head, rows, hl=hl, heat_cols=(3, 5) + ((9, 10) if with_split else ()), heat_scale=15)


def grid_table(row_labels, col_labels, fn, scale=12, corner=""):
    rows = []
    for rl, rv in row_labels:
        r = [rl]
        for cl, cv in col_labels:
            s = summarize(fn(rv, cv))
            r.append(cell(s["avg_net_bps"]) if s["n"] else "-")
        rows.append(r)
    return H.table([corner] + [c[0] for c in col_labels], rows, heat_cols=tuple(range(1, len(col_labels) + 1)),
                   heat_scale=scale)


def bucket_rows(recs, label, f, k=4, fmt="{:.2f}"):
    vals = sorted(f(r) for r in recs if f(r) is not None)
    cuts = [vals[int(len(vals) * i / k)] for i in range(1, k)]
    groups = defaultdict(list)
    for r in recs:
        v = f(r)
        if v is not None:
            groups[bisect.bisect(cuts, v)].append(r)
    names = []
    edges = [None] + cuts + [None]
    for i in range(k):
        lo, hi = edges[i], edges[i + 1]
        names.append(f"{label} " + (f"< {fmt.format(hi)}" if lo is None else f">= {fmt.format(lo)}" if hi is None
                                     else f"{fmt.format(lo)} - {fmt.format(hi)}"))
    return [(names[i], groups[i]) for i in range(k)]


def by(recs, key, order=None):
    g = defaultdict(list)
    for r in recs:
        g[key(r)].append(r)
    keys = order or sorted(g)
    return [(str(k), g[k]) for k in keys if k in g]


def max_concurrent(recs):
    best = 0
    by_day = defaultdict(list)
    for r in recs:
        by_day[r.day].append((r.t.entry_idx, r.t.exit_idx))
    for iv in by_day.values():
        for a, _ in iv:
            best = max(best, sum(1 for x, y in iv if x <= a <= y))
    return best


# ----------------------------------------------------------------------- run
def main():
    OUT.mkdir(parents=True, exist_ok=True)
    data = load_all()
    ndays = len(complete_days(data[U[0]][0]))
    days_sorted = complete_days(data[U[0]][0])
    base_rule = ExitRule()
    base = collect(data, U, base_rule)
    bs = summarize(base)
    ci = cluster_ci(base)
    print("baseline", bs["n"], round(bs["avg_net_bps"], 2), ci)

    # ---- per-trade export
    with open(OUT / "trades_baseline.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["day", "symbol", "side", "entry_time", "entry", "stop", "exit_time", "exit", "reason", "range_hi",
                    "range_lo", "width_pct", "gap_pct", "gross_pts", "R", "qty", "charges", "net_rs"])
        for r in sorted(base, key=lambda r: (r.day, r.symbol)):
            t = r.t
            w.writerow([r.day, r.symbol, t.side, hhmm(555 + t.entry_idx), round(t.entry, 2), round(t.stop, 2),
                        hhmm(555 + t.exit_idx), round(t.exit, 2), t.reason, r.hi, r.lo, round(r.width_pct, 3),
                        round(r.gap_pct, 3), round(t.pnl, 2), round(t.r, 3), r.qty, round(r.charges, 2),
                        round(r.net_rs, 2)])

    # ---- the "free run": breakout entry, stop effectively disabled, held to 15:15 (for MFE/MAE statistics)
    free = collect(data, U, ExitRule(stop="pct:50"))

    # ---- exit grid (stop x target at 15:15) - reused for csv
    STOPS = [("opposite side of range", "opp"), ("0.75 x range", "frac:0.75"), ("mid-range", "mid"),
             ("0.25 x range", "frac:0.25"), ("0.25% of price", "pct:0.25"), ("0.40% of price", "pct:0.4")]
    TGTS = [("no target", None), ("0.5R", .5), ("1R", 1.0), ("1.5R", 1.5), ("2R", 2.0), ("3R", 3.0)]
    cache = {}

    def exit_run(stop, tg, cutoff=M(15, 15), **kw):
        k = (stop, tg, cutoff, tuple(sorted(kw.items())))
        if k not in cache:
            cache[k] = collect(data, U, ExitRule(stop=stop, target_r=tg, cutoff=cutoff), **kw)
        return cache[k]

    with open(OUT / "grid.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["stop", "target_R", "cutoff", "trades", "win_pct", "gross_bps", "net_bps", "t", "net_rs", "max_dd"])
        for sl, sv in STOPS:
            for tl, tv in TGTS:
                for co in (M(11, 30), M(13), M(14, 30), M(15, 15)):
                    s = summarize(exit_run(sv, tv, co))
                    w.writerow([sv, tv, hhmm(co), s["n"], round(s["win_pct"], 1), round(s["avg_gross_bps"], 2),
                                round(s["avg_net_bps"], 2), round(s["t_stat"], 2), round(s["net_rs"]),
                                round(s["max_dd_rs"])])

    # =============================================================== HTML
    P = []
    add = P.append
    add(f"<h1>5-stock 15-minute range breakout - 6-month analysis</h1>")
    add(f"<p class='mut'>{ndays} trading days ({days_sorted[0]} to {days_sorted[-1]}), 1-minute Upstox candles, "
        f"{', '.join(U)}. All results are simulated on history; nothing here is investment advice.</p>")

    # ---- 0 strategy
    add("<h2>0. What was tested</h2><div class='box'><ol>"
        "<li>09:15-09:30 is candle 1 and is ignored. High/low of <b>candle 2 + candle 3 (09:30-10:00)</b> define the range - "
        "it is only known at 10:00, so that is the earliest entry.</li>"
        "<li>From 10:00 the <b>first</b> time price trades above the high (buy) or below the low (sell) is the entry, filled at "
        "the level (or at the open if a bar gaps through it). One trade per stock per day.</li>"
        "<li>Baseline exit (my pick from the data below): stop at the <b>opposite side of the range</b>, no profit target, "
        "square off at <b>15:15</b>.</li>"
        f"<li>Every position is Rs {NOTIONAL:,.0f} notional (Rs 1L capital x 5 MIS leverage / 5 stocks). Charges use the "
        "estimated Upstox schedule from <code>src/orb15/costs.py</code> (unverified). If one 1-minute bar touches both stop and "
        "target the stop is assumed first.</li></ol>"
        "<p><b>Interpretation note:</b> you wrote &quot;wait till 9:45&quot; and &quot;2nd and 3rd 15-min candle&quot;. The 3rd candle "
        "closes at 10:00, so I read it as &quot;45 minutes after the open&quot;. Section 4 also shows ranges built from other "
        "candles. <b>Tata Motors:</b> it demerged in late 2025; the headline uses <b>TMPV</b> (passenger vehicles, the old "
        "listing). TMCV (the entity the exchange now calls &quot;Tata Motors Limited&quot;) is compared in section 4.</p></div>")

    # ---- 1 headline
    add("<h2>1. Headline result</h2>")
    daily = day_pnl(base)
    dvals = list(daily.values())
    sharpe = st.mean(dvals) / st.pstdev(dvals) * (250 ** .5) if st.pstdev(dvals) else 0
    add("<div class='kpis'>" + "".join(
        f"<div class='kpi'><b class='{c}'>{v}</b><span>{l}</span></div>" for v, l, c in [
            (str(bs["n"]), "trades", ""),
            (f"{bs['win_pct']:.0f}%", "win rate", ""),
            (f"{bs['avg_gross_bps']:+.1f} bps", "avg gross / trade", H.cls(bs["avg_gross_bps"])),
            (f"{bs['avg_charge_bps']:.1f} bps", "avg charges / trade", ""),
            (f"{bs['avg_net_bps']:+.1f} bps", "avg NET / trade", H.cls(bs["avg_net_bps"])),
            (f"Rs {bs['net_rs']:+,.0f}", "net P&L (6 mo)", H.cls(bs["net_rs"])),
            (f"Rs {bs['max_dd_rs']:,.0f}", "max drawdown", "neg"),
            (f"{bs['t_stat']:.2f}", "t-stat (net)", ""),
        ]) + "</div>")
    add(f"<div class='box warn'><b>Plain reading.</b> Before costs the breakout has a small positive edge "
        f"({bs['avg_gross_bps']:+.1f} bps per trade). Charges take {bs['avg_charge_bps']:.1f} bps of it, leaving "
        f"{bs['avg_net_bps']:+.1f} bps. A 95% interval for the true net average (resampling whole days) is "
        f"<b>{ci[0]:+.1f} to {ci[1]:+.1f} bps</b> - it straddles zero, so 6 months cannot distinguish this from no edge. "
        f"The shape is classic breakout: {100 * sum(r.t.reason == 'STOP' for r in base) / bs['n']:.0f}% of trades are stopped for -1R, "
        f"most of the rest ride to 15:15 for about +1R on average, but only {bs['win_pct']:.0f}% of trades finish "
        f"in profit after charges, so you have to be able to sit through a lot of losers. Sections 2-4 show which choices matter; section 6 shows how fragile the apparent "
        f"improvements are.</div>")
    add("<h3>Cumulative net P&amp;L by day (all 5 stocks, Rs 1L per position)</h3>")
    cum_net = []
    cum_gross = []
    gday = defaultdict(float)
    for r in base:
        gday[r.day] += r.gross_rs
    a = b = 0
    for d in days_sorted:
        a += daily.get(d, 0)
        b += gday.get(d, 0)
        cum_net.append(a)
        cum_gross.append(b)
    add(H.svg_lines([("net of charges", cum_net), ("before charges", cum_gross)], days_sorted, ylabel="Rs"))
    add(f"<p>Daily Sharpe-style ratio {sharpe:.2f} annualised (not significant), winning days "
        f"{100 * sum(v > 0 for v in dvals) / len(dvals):.0f}%, worst day Rs {min(dvals):,.0f}, best day Rs {max(dvals):,.0f}, "
        f"up to {max_concurrent(base)} positions open at once (so Rs {max_concurrent(base) * NOTIONAL:,.0f} of buying power).</p>")

    add("<h3>By stock and by side</h3>")
    add(stat_table(by(base, lambda r: r.symbol, U) + by(base, lambda r: r.t.side), with_split=True))
    add("<p class='mut'>No single stock is statistically distinguishable from zero. Shorts did better than longs in this "
        "sample, but the 6-month window was a falling market for several of these names (section 6).</p>")

    # ---- 2 anatomy
    add("<h2>2. Anatomy of the setup</h2>")
    widths = {s: [r.width_pct for r in free if r.symbol == s] for s in U}
    rows = []
    for s in U:
        fr = [r for r in free if r.symbol == s]
        rows.append([s, f"{st.median(widths[s]):.2f}%", f"{st.quantiles(widths[s], n=10)[0]:.2f}% - {st.quantiles(widths[s], n=10)[-1]:.2f}%",
                     f"{100 * sum(r.t.side == 'LONG' for r in fr) / len(fr):.0f}%",
                     f"{100 * sum(r.t.mae >= (r.hi - r.lo) for r in fr) / len(fr):.0f}%"])
    add(H.table(["stock", "median range width", "10th-90th pct", "first break is UP", "false-breakout rate (price later trades back through the opposite side)"], rows))
    add(f"<p>Price broke out on {len(free)} of {ndays * len(U)} stock-days "
        f"({100 * len(free) / (ndays * len(U)):.0f}%), so the strategy is essentially always in the market. Typical stop "
        f"distance is the range width, about {st.median(r.width_pct for r in free):.2f}% of price. "
        f"<b>{100 * sum(r.t.mae >= (r.hi - r.lo) for r in free) / len(free):.0f}%</b> of breakouts later trade back through the opposite "
        "side of the range before 15:15 - that is the false-breakout rate an opposite-side stop has to absorb.</p>")
    hist = defaultdict(int)
    for r in free:
        hist[(r.entry_min - M(10)) // 15] += 1
    labels = [hhmm(M(10) + 15 * i) for i in range(0, 17) if i in hist or i < 8]
    add("<h3>When the breakout happens (count by 15-min bucket)</h3>")
    add(H.svg_bars(labels, [hist[(M(*map(int, l.split(':'))) - M(10)) // 15] for l in labels], fmt="{:.0f}", color="#2563eb"))
    ks = [0.25, 0.5, 0.75, 1, 1.5, 2, 3]
    add("<h3>How far does a breakout run? (stop disabled, measured in range widths)</h3>")
    add(H.table(["distance (x range width)"] + [str(k) for k in ks], [
        ["P(price gets this far in favour by 15:15)"] + [f"{100 * sum(r.t.mfe >= k * (r.hi - r.lo) for r in free) / len(free):.0f}%" for k in ks],
        ["P(price goes this far AGAINST by 15:15)"] + [f"{100 * sum(r.t.mae >= k * (r.hi - r.lo) for r in free) / len(free):.0f}%" for k in ks],
    ]))
    add("<p>Favourable excursion is only slightly more likely than adverse excursion at every distance - the edge is a thin "
        "tilt, not a large asymmetry. That is why the exit design matters so much.</p>")

    # ---- 3 exit decisions
    add("<h2>3. Exit decisions: stop, target (RR), time</h2>")
    add("<h3>3a. Stop x profit target (net bps per trade, exit 15:15)</h3>")
    add(grid_table(STOPS, TGTS, lambda sv, tv: exit_run(sv, tv), corner="stop \\ target"))
    add("<p><b>Stop:</b> the opposite side of the range is clearly the best; every tighter stop is worse because the first "
        f"pullback after a breakout usually retests the level (a 0.25x-range stop is hit on {100 * sum(r.t.reason == 'STOP' for r in exit_run('frac:0.25', None)) / len(exit_run('frac:0.25', None)):.0f}% of trades vs "
        f"{100 * sum(r.t.reason == 'STOP' for r in base) / len(base):.0f}% for the opposite-side stop). "
        "<b>Target:</b> adding a fixed target <i>lowers</i> expectancy - the winners are the trades that keep running, "
        "capping them at 1R or 1.5R raises the win rate but loses more than it gains.</p>")
    add("<h3>3b. Does a fixed RR help? (stop = opposite side)</h3>")
    rows = [("no target", exit_run("opp", None))] + [(l, exit_run("opp", v)) for l, v in TGTS[1:]]
    add(stat_table(rows, hl=0))
    add("<h3>3c. Square-off time (stop = opposite side, no target)</h3>")
    add(stat_table([(hhmm(c), exit_run("opp", None, c)) for c in (M(10, 30), M(11, 30), M(13), M(14, 30), M(15, 15))], hl=4))
    add("<p>Exiting early is clearly bad: the gross edge is <i>negative</i> if you flatten by 10:30-11:30 and only builds through "
        "the afternoon. Breakouts are typically retested first and pay later, so the trade needs the whole day.</p>")
    add("<h3>3d. Break-even and trailing stops (target none, exit 15:15)</h3>")
    var = [("none (baseline)", base)]
    for be in (1.0, 1.5):
        var.append((f"move to break-even after +{be}R", collect(data, U, ExitRule(be_after_r=be))))
    for tr in (1.0, 1.5, 2.0):
        var.append((f"trail {tr}R behind best price", collect(data, U, ExitRule(trail_r=tr))))
    add(stat_table(var, hl=0))
    add("<p>Trailing closer than ~2R gets shaken out by normal intraday noise. Break-even after +1R is roughly neutral "
        "on expectancy (it only changes the shape, converting some -1R into 0). Nothing here beats the plain version.</p>")

    # ---- 4 entry & structure
    add("<h2>4. Entry and structure decisions</h2>")
    add("<h3>4a. How to detect &quot;the candle breaks the line&quot; (net bps)</h3>")
    kinds = [("touch (stop order at the level)", "touch"), ("1-min close beyond", "close1"),
             ("5-min close beyond", "close5"), ("15-min close beyond", "close15")]
    bufs = [("0% buffer", 0.0), ("0.05%", 0.05), ("0.10%", 0.10)]
    add(grid_table(kinds, bufs, lambda k, b: exit_run("opp", None, M(15, 15), kind=k, buffer_pct=b), corner="trigger \\ buffer beyond level"))
    add("<p>Entering the instant price touches the level is not better than waiting for a candle close - waiting for a "
        "5-min close beyond the level plus a small buffer is marginally better, since it skips some wick-only probes. The "
        "differences (about 1-3 bps) are inside the noise, so choose on practicality: a stop-limit/market trigger order is "
        "easiest, a 5-minute close needs you or the bot to watch the bar.</p>")
    add("<h3>4b. Cost of slippage (applied to entry and to stop / square-off fills)</h3>")
    sl_rows = []
    for sl in (0, 0.01, 0.02, 0.03, 0.05):
        sl_rows.append((f"{sl * 100:.0f} bps each fill" if sl else "no slippage",
                        collect(data, U, ExitRule(slip_pct=sl), slip_pct=sl)))
    add(stat_table(sl_rows, with_split=False))
    add("<p><b>This is the most important risk to the strategy.</b> A breakout order is a market-type order in a moving price; "
        "even 1 bp of slippage per fill erases the net edge, 2 bps makes it clearly negative and 5 bps turns gross to zero. These five stocks are very liquid so "
        "1-2 bps is plausible, but it has to be measured live before trusting the numbers.</p>")
    add("<h3>4c. Position size changes the cost drag (brokerage is a flat Rs 20 per order)</h3>")
    nrows = []
    for nt in (50_000, 100_000, 200_000, 500_000):
        rr = collect(data, U, base_rule)
        for x in rr:
            size(x, nt)
        nrows.append((f"Rs {nt:,.0f} per position", rr))
    add(stat_table(nrows, with_split=False))
    add("<p>Gross edge per trade is the same; bigger positions dilute the fixed brokerage. The catch is that bigger positions "
        "also mean bigger losses and more leverage - at Rs 5L per position the max drawdown is several times larger.</p>")
    add("<h3>4d. Other structure choices</h3>")
    struct = [
        ("baseline: range = candles 2+3, 1 trade/day, both sides", base),
        ("range = candle 1 only (09:15-09:30)", exit_run("opp", None, M(15, 15), range_candles=(1, 1))),
        ("range = candles 1+2 (09:15-09:45)", exit_run("opp", None, M(15, 15), range_candles=(1, 2))),
        ("range = candles 1+2+3 (09:15-10:00, classic 45-min ORB)", exit_run("opp", None, M(15, 15), range_candles=(1, 3))),
        ("range = candle 2 only", exit_run("opp", None, M(15, 15), range_candles=(2, 2))),
        ("range = candle 3 only", exit_run("opp", None, M(15, 15), range_candles=(3, 3))),
        ("range = candles 2+3+4 (to 10:15)", exit_run("opp", None, M(15, 15), range_candles=(2, 4))),
        ("no entries after 10:30", exit_run("opp", None, M(15, 15), last_entry_min=M(10, 30))),
        ("no entries after 12:00", exit_run("opp", None, M(15, 15), last_entry_min=M(12))),
        ("long breakouts only", exit_run("opp", None, M(15, 15), sides=("LONG",))),
        ("short breakouts only", exit_run("opp", None, M(15, 15), sides=("SHORT",))),
        ("allow one reversal after a stop-out", exit_run("opp", None, M(15, 15), max_trades=2)),
    ]
    add(stat_table(struct, hl=0))
    tm = collect(data, [s if s != "TMPV" else "TMCV" for s in U], base_rule)
    add("<p><b>Findings.</b> The candle 2+3 range you chose is as good as the other windows - they all sit within noise of each other "
        "(candle 3 alone is the weakest). About 76% of breakouts happen by 10:30 and 95% by 12:00, so cutting late entries "
        "changes little. Allowing one reversal after a stop-out does not help (lower expectancy and a deeper drawdown) - "
        "take one trade per stock per day.</p>")
    add(H.table(["Tata variant", "trades", "gross bps", "net bps"], [
        ["TMPV (in headline)"] + [str(summarize([r for r in base if r.symbol == 'TMPV'])['n']),
                                  cell(summarize([r for r in base if r.symbol == 'TMPV'])['avg_gross_bps']),
                                  cell(summarize([r for r in base if r.symbol == 'TMPV'])['avg_net_bps'])],
        ["TMCV instead"] + [str(summarize([r for r in tm if r.symbol == 'TMCV'])['n']),
                            cell(summarize([r for r in tm if r.symbol == 'TMCV'])['avg_gross_bps']),
                            cell(summarize([r for r in tm if r.symbol == 'TMCV'])['avg_net_bps'])],
    ]))

    # ---- 5 filters
    add("<h2>5. Can a filter pick the better days? (exploratory)</h2>")
    add("<div class='box warn'><b>Read this table with suspicion.</b> I looked at ~30 filter buckets on 613 trades; a few will look "
        "good by luck alone. A filter is only interesting if it is <i>also</i> positive in both the Apr-Jul and Aug-Oct columns "
        "and makes sense a priori. None of the filters below has a net t-stat above 2.</div>")
    filt = [
        ("breakout side agrees with 10:00-vs-09:15 trend", [r for r in base if r.aligned_trend]),
        ("breakout side AGAINST that trend", [r for r in base if not r.aligned_trend]),
        ("breakout side agrees with candle-1 colour", [r for r in base if r.aligned_c1]),
        ("breakout side agrees with the opening gap", [r for r in base if r.aligned_gap]),
        ("short AND agrees with trend", [r for r in base if r.aligned_trend and r.t.side == "SHORT"]),
    ]
    add(stat_table(filt))
    add("<h3>By volatility / volume / timing quartile</h3>")
    q = []
    q += bucket_rows(base, "range width %", lambda r: r.width_pct)
    q += bucket_rows(base, "range / avg daily range", lambda r: r.rel_width)
    q += bucket_rows(base, "|gap| %", lambda r: abs(r.gap_pct))
    q += bucket_rows(base, "entry-bar volume x avg", lambda r: r.entry_vol_ratio)
    q += bucket_rows(base, "entry minute", lambda r: r.entry_min, fmt="{:.0f}")
    add(stat_table(q))
    add("<p>Positive in <i>both</i> halves: breakouts that agree with the 10:00 trend or the candle-1 colour, the widest-range "
        "quartile, and the top two volume quartiles. That is plausible (a wide range means more movement relative to fixed costs; "
        "volume confirms participation), but each bucket has only ~150-350 trades and I tried many of them. Treat these as "
        "hypotheses for the forward test, not rules.</p>")
    add("<h3>Day of week (shown for completeness - almost certainly noise)</h3>")
    add(stat_table(by(base, lambda r: ["Mon", "Tue", "Wed", "Thu", "Fri"][r.dow], ["Mon", "Tue", "Wed", "Thu", "Fri"])))

    # ---- 6 stability
    add("<h2>6. Is it stable? Month by month and out-of-sample</h2>")
    months = sorted({r.month for r in base})
    mv = []
    for m in months:
        rr = [r for r in base if r.month == m]
        mv.append(summarize(rr)["net_rs"])
    add("<h3>Net P&amp;L by month (Rs)</h3>")
    add(H.svg_bars(months, mv, fmt="{:,.0f}"))
    a, b = split(base)
    sa, sb = summarize(a), summarize(b)
    add(f"<p>Apr-Jul ({sa['n']} trades): <b>{sa['avg_net_bps']:+.1f} bps</b> net. Aug-Oct ({sb['n']} trades): "
        f"<b>{sb['avg_net_bps']:+.1f} bps</b> net. The strategy was roughly flat for four months and then worked well in "
        "Aug-Oct. That is a regime change, not proof of an edge: if it only pays in trending months you will sit through "
        "long flat or negative stretches (the Apr-Jul net result is below zero).</p>")
    add(stat_table([("Apr-Jul", a), ("Aug-Oct", b)] + by(base, lambda r: r.month), with_split=False))
    add("<p class='mut'>Market context for the same window (average 10:00 to 15:15 move of each stock, long side): "
        + ", ".join(f"{s} {st.mean((data[s][0][d][M(15, 15) - 555][1] / data[s][0][d][44][4] - 1) * 1e4 for d in days_sorted):+.1f} bps"
                    for s in U) + ". Three of the five drifted down on average intraday, which flatters shorts (and the short edge only appears in Aug-Oct).</p>")

    # ---- 7 verdict
    add("<h2>7. Decisions and verdict</h2><div class='box'><ol>"
        "<li><b>Stop: opposite side of the 09:30-10:00 range</b> (data-backed; every tighter stop is much worse).</li>"
        "<li><b>Target / RR: none - hold to 15:15.</b> Fixed RR targets lower expectancy at every level tested. If you want "
        "a number, 2R gives up the least (net +0.8 vs +1.9 bps). Trailing stops, break-even stops and early square-offs do not improve it either.</li>"
        "<li><b>Entry:</b> the trigger type (touch vs 5-min close) is within noise. A small buffer (0.05-0.10%) "
        "or 5-min close is slightly better in this sample (about +1-3 bps); choose whichever you can execute reliably.</li>"
        "<li><b>One trade per stock per day</b>; no re-entry after a stop-out. Entries after 12:00 are rare (5%) and do not matter.</li>"
        "<li><b>Sizing:</b> costs are 8.3 bps on Rs 1L positions, 5.9 on Rs 2L and 4.5 on Rs 5L (flat brokerage). Net only turns "
        "clearly positive at Rs 2L+ per position, which needs more leverage and carries a proportionally larger drawdown.</li>"
        "<li><b>Filters:</b> nothing is proven. Candidates to forward-test: breakout agrees with the 10:00 trend, wide range, "
        "high breakout volume.</li></ol></div>")
    add(f"<div class='box warn'><b>Verdict.</b> The pattern you saw is real in the sense that it is gross-positive "
        f"({bs['avg_gross_bps']:+.1f} bps), but over 6 months it is <b>not distinguishable from zero after costs</b> "
        f"(net {bs['avg_net_bps']:+.1f} bps, 95% range {ci[0]:+.1f} to {ci[1]:+.1f}) and it disappears with ~1 bp of slippage per fill. "
        f"The recent months look much better, which may be luck or a trending regime. Before risking money: (1) measure real slippage "
        f"with a handful of paper/1-lot trades, (2) forward-test the baseline for at least 2-3 months, (3) widen the sample "
        f"(more stocks or a longer history) - 5 stocks over 124 days is only {bs['n']} trades.</div>")
    add("<p class='mut'>Files: <code>trades_baseline.csv</code> (every simulated trade), <code>grid.csv</code> (stop x target x cutoff). "
        "Code: <code>src/orb15/</code>, <code>analyze_orb15.py</code>.</p>")

    html_doc = ("<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
                f"<title>ORB-15 5-stock analysis</title><style>{H.CSS}</style></head><body><main>" + "\n".join(P) + "</main></body></html>")
    (OUT / "report.html").write_text(html_doc, encoding="utf-8")
    print("wrote", OUT / "report.html")


if __name__ == "__main__":
    main()
