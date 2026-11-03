"""Main backtest: the v2 top-down ORB strategy over the cached candle history."""

from datetime import date

from src.backtest.history import History, load_history
from src.backtest.snapshots import compute_day_snapshots, taken_trades
from src.strategy.params import DEFAULT_PARAMS, StrategyParams


def run_backtest(
    start_date: date | str | None = None,
    end_date: date | str | None = None,
    params: StrategyParams = DEFAULT_PARAMS,
    history: History | None = None,
) -> list[dict]:
    """Trades the strategy would have taken over [start_date, end_date] (default: all cached days).

    Each trade dict is orb_engine.simulate_trade's output plus the
    context that qualified it (date, sector, symbol, stock/sector move,
    volume ratios, VIX, NIFTY trend) and `net_r`, its R multiple after costs.
    """
    history = history or load_history()
    days = compute_day_snapshots(
        history, params, str(start_date) if start_date else None, str(end_date) if end_date else None
    )
    return taken_trades(days)
