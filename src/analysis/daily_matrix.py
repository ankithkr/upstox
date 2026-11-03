"""Per-day sector and stock snapshots for the manual-backtest UI.

A thin wrapper over src.backtest.snapshots, which walks the full
strategy funnel for each day and keeps every step's result (gate,
sectors, stocks, filters, simulated trade) so the heatmap can show why
something was or wasn't traded.
"""

from src.backtest.history import load_history
from src.backtest.snapshots import compute_day_snapshots
from src.strategy.params import DEFAULT_PARAMS, StrategyParams


def compute_days(start_date=None, end_date=None, params: StrategyParams = DEFAULT_PARAMS, history=None) -> dict:
    history = history or load_history()
    days = compute_day_snapshots(
        history, params, str(start_date) if start_date else None, str(end_date) if end_date else None
    )
    return {
        "days": {d["date"]: d for d in days},
        "missing_symbols": history.missing_symbols,
        "start": days[0]["date"] if days else None,
        "end": days[-1]["date"] if days else None,
    }
