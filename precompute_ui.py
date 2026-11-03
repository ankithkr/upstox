"""Build the JSON files the local backtest UI reads.

Runs the strategy once over every day the Upstox candle cache covers
(src.backtest.snapshots) and writes:

    data_cache/ui_backtest.json   - dashboard summary + every trade taken
    data_cache/ui_daily.json      - per-day regime / sector / stock snapshots,
                                    including the filters and trades behind them

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

from src.backtest import dashboard
from src.backtest.history import load_history
from src.backtest.reference_values import trading_days
from src.backtest.snapshots import compute_day_snapshots, taken_trades
from src.data.indices import NIFTY_50_INSTRUMENT_KEY
from src.integrations.upstox_history import CACHE_DIR, get_candles
from src.strategy.params import DEFAULT_PARAMS

DAILY_LOOKBACK_BUFFER_DAYS = 10

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


def build_payloads(history, params=DEFAULT_PARAMS) -> tuple[dict, dict]:
    days = compute_day_snapshots(history, params)
    trades = taken_trades(days)
    start, end = days[0]["date"], days[-1]["date"]
    gate_open = sum(1 for d in days if d["gate_ok"])

    backtest = {
        "params": params.as_dict(),
        "overview": dashboard.overview(trades, start, end, len(days), gate_open),
        "key_metrics": dashboard.key_metrics(trades),
        "equity_curve": dashboard.equity_curve(trades),
        "outcome_breakdown": [list(r) for r in dashboard.outcome_breakdown(trades)],
        "by_year": [list(r) for r in dashboard.by_year(trades)],
        "by_month": [list(r) for r in dashboard.by_month(trades)],
        "by_sector": [list(r) for r in dashboard.by_sector(trades)],
        "by_direction": [list(r) for r in dashboard.by_direction(trades)],
        "trades": trades,
    }
    daily = {
        "days": {d["date"]: d for d in days},
        "missing_symbols": history.missing_symbols,
        "start": start,
        "end": end,
    }
    return backtest, daily


def main():
    print("Loading cached candles...")
    history = load_history()
    print(f"  {len(history.stock_5m)} stocks, {len(history.days)} NIFTY days")

    print("Running strategy over every cached day...")
    backtest, daily = build_payloads(history)
    ov = backtest["overview"]
    print(f"  {ov['start_date']} -> {ov['end_date']}: {ov['trading_days']} days, "
          f"{ov['gate_open_days']} gate-open, {ov['total_signals']} trades on {ov['days_traded']} days")

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(f"{OUT_DIR}/ui_backtest.json", "w") as f:
        json.dump(backtest, f, separators=(",", ":"))
    with open(f"{OUT_DIR}/ui_daily.json", "w") as f:
        json.dump(daily, f, separators=(",", ":"))
    if daily["missing_symbols"]:
        print(f"  (no cached candles for: {', '.join(daily['missing_symbols'])})")
    print("Done.")


if __name__ == "__main__":
    main()
