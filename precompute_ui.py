"""Build the JSON files the local backtest UI reads.

Runs the full ORB backtest and the per-day sector/stock matrix over
whatever range the Upstox candle cache covers, and writes:

    data_cache/ui_backtest.json   - dashboard summary + every trade
    data_cache/ui_daily.json      - per-day sector & stock 09:30 snapshots

Rerun after refreshing the candle cache. The UI also has a "Rebuild"
button that shells out to this script.
"""

import json
import os
import re
from datetime import date, timedelta
from pathlib import Path

# Serve candles only from the local cache; never call Upstox at build time.
os.environ.setdefault("UPSTOX_OFFLINE", "1")

from src.analysis.daily_matrix import DAILY_LOOKBACK_BUFFER_DAYS, compute_days
from src.backtest import dashboard
from src.backtest.reference_values import trading_days
from src.backtest.runner import run_backtest
from src.integrations.upstox_history import CACHE_DIR, get_candles
from src.data.indices import NIFTY_50_INSTRUMENT_KEY

OUT_DIR = "data_cache"

_RANGE_RE = re.compile(r"_days_1_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})\.csv$")


def _cached_range() -> tuple[date, date]:
    """Widest [start, end] the equity daily-candle cache fully covers.

    The strategy needs each stock's prior-day close, so the usable
    backtest window is bounded by what's cached for the *stocks*, not
    the indices (whose intraday history often reaches further back).
    `run_backtest` asks for daily candles from start_date minus the
    lookback buffer, so we add that buffer back here.
    """
    ranges: dict[tuple[str, str], int] = {}
    for path in Path(CACHE_DIR).glob("NSE_EQ_*_days_1_*.csv"):
        m = _RANGE_RE.search(path.name)
        if m:
            ranges[(m.group(1), m.group(2))] = ranges.get((m.group(1), m.group(2)), 0) + 1
    if not ranges:
        raise SystemExit(
            "No cached equity daily candles in data_cache/candles. Run the "
            "backtest/update scripts once (online) to populate the cache."
        )
    # The window most stocks share (ties broken by widest span) - so the
    # heatmaps aren't riddled with gaps for stocks that only got a
    # shorter backfill.
    (raw_start, raw_end), _ = max(
        ranges.items(),
        key=lambda kv: (kv[1], (date.fromisoformat(kv[0][1]) - date.fromisoformat(kv[0][0])).days),
    )
    start_date = date.fromisoformat(raw_start) + timedelta(days=DAILY_LOOKBACK_BUFFER_DAYS)
    end_date = date.fromisoformat(raw_end)

    candles = get_candles(NIFTY_50_INSTRUMENT_KEY, "minutes", "15", start_date, end_date)
    if not candles:
        raise SystemExit("NIFTY 50 15m candles not cached for the resolved range.")
    days = trading_days(candles)
    return date.fromisoformat(days[0]), date.fromisoformat(days[-1])


def build_backtest(start_date: date, end_date: date) -> dict:
    trades = run_backtest(start_date, end_date)
    nifty_15m = get_candles(NIFTY_50_INSTRUMENT_KEY, "minutes", "15", start_date, end_date)
    days_count = len(trading_days(nifty_15m))

    return {
        "overview": dashboard.overview(trades, start_date, end_date, days_count),
        "key_metrics": dashboard.key_metrics(trades),
        "outcome_breakdown": [list(r) for r in dashboard.outcome_breakdown(trades)],
        "by_month": [list(r) for r in dashboard.by_month(trades)],
        "by_sector": [list(r) for r in dashboard.by_sector(trades)],
        "by_direction": [list(r) for r in dashboard.by_direction(trades)],
        "trades": [
            {k: (str(v) if isinstance(v, date) else v) for k, v in t.items()}
            for t in trades
        ],
    }


def main():
    start_date, end_date = _cached_range()
    print(f"Cache covers {start_date} to {end_date}")

    print("Running backtest...")
    backtest = build_backtest(start_date, end_date)
    with open(f"{OUT_DIR}/ui_backtest.json", "w") as f:
        json.dump(backtest, f)
    print(f"  {len(backtest['trades'])} trades")

    print("Building per-day matrix...")
    daily = compute_days(start_date, end_date)
    with open(f"{OUT_DIR}/ui_daily.json", "w") as f:
        json.dump(daily, f)
    print(f"  {len(daily['days'])} trading days")
    if daily["missing_symbols"]:
        print(f"  (no instrument key for: {', '.join(daily['missing_symbols'])})")

    print("Done.")


if __name__ == "__main__":
    main()
