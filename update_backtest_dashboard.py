"""Run the top-down ORB backtest over the cached candles and write results to Google Sheets.

'Backtest dahboard' (sheet 1, renamed by hand) gets the summary
tables; 'Backtest Trades' gets the raw list of every trade taken.
Rerunning refreshes both in place. Reads the local candle cache only -
run `python refresh_cache.py` first to bring it up to date.
"""

from src.backtest import dashboard
from src.backtest.history import load_history
from src.backtest.snapshots import compute_day_snapshots, taken_trades
from src.integrations.google_sheets import get_or_create_worksheet, get_spreadsheet

DASHBOARD_SHEET = "Backtest dahboard"  # matches the sheet name as renamed in the spreadsheet
TRADES_SHEET = "Backtest Trades"


def _group_header(label):
    return [label, "Trades", "Target hit", "Target hit %", "Net R", "Net R / trade"]

TRADE_COLUMNS = [
    "date",
    "sector",
    "symbol",
    "direction",
    "market_bias",
    "sector_change",
    "stock_change",
    "vix",
    "nifty_trend",
    "open_vol_ratio",
    "breakout_vol_ratio",
    "breakout_time",
    "entry_time",
    "entry_price",
    "stop_loss",
    "risk_pct",
    "target",
    "outcome",
    "exit_time",
    "exit_price",
    "hold_minutes",
    "r_multiple",
    "net_r",
]


def write_trades_sheet(spreadsheet, trades: list[dict]):
    worksheet = get_or_create_worksheet(
        spreadsheet, TRADES_SHEET, rows=len(trades) + 1, cols=len(TRADE_COLUMNS)
    )
    worksheet.clear()
    rows = [TRADE_COLUMNS] + [[t.get(c) for c in TRADE_COLUMNS] for t in trades]
    worksheet.update(values=rows, range_name="A1")
    return worksheet


def write_dashboard_sheet(spreadsheet, trades: list[dict], start_date, end_date, days_count, gate_open_days):
    worksheet = spreadsheet.worksheet(DASHBOARD_SHEET)
    worksheet.clear()

    ov = dashboard.overview(trades, start_date, end_date, days_count, gate_open_days)
    metrics = dashboard.key_metrics(trades)

    rows = [
        ["Backtest Dashboard"],
        [],
        ["Period", f"{ov['start_date']} to {ov['end_date']}"],
        ["Trading days", ov["trading_days"]],
        ["Total signals", ov["total_signals"]],
        ["Unique signals (date + symbol + direction)", ov["unique_signals"]],
        [],
        ["Regime-gate-open days", ov["gate_open_days"]],
        ["Days traded", ov["days_traded"]],
        [],
        ["Net R per trade (after costs)", metrics["avg_net_r"]],
        ["Total net R", metrics["total_net_r"]],
        ["Profit factor", metrics["profit_factor"]],
        ["Max drawdown (R)", metrics["max_drawdown_r"]],
        ["Profitable trades", f"{metrics['profitable_pct']}%"],
        ["Hit target", f"{metrics['win_rate_pct']}%"],
        ["Avg stop (% of price)", metrics["avg_stop_pct"]],
        ["Avg hold time - all trades (min)", metrics["avg_hold_minutes"]],
        [],
        ["Outcome", "Count", "% of total"],
        *[list(r) for r in dashboard.outcome_breakdown(trades)],
        [],
        _group_header("Year"),
        *[list(r) for r in dashboard.by_year(trades)],
        [],
        _group_header("Month"),
        *[list(r) for r in dashboard.by_month(trades)],
        [],
        _group_header("Sector"),
        *[list(r) for r in dashboard.by_sector(trades)],
        [],
        _group_header("Direction"),
        *[list(r) for r in dashboard.by_direction(trades)],
    ]

    worksheet.update(values=rows, range_name="A1")
    return worksheet


def main():
    spreadsheet = get_spreadsheet()

    print("Running backtest over the cached candles...")
    days = compute_day_snapshots(load_history())
    trades = taken_trades(days)
    gate_open_days = sum(1 for d in days if d["gate_ok"])

    write_trades_sheet(spreadsheet, trades)
    write_dashboard_sheet(spreadsheet, trades, days[0]["date"], days[-1]["date"], len(days), gate_open_days)

    print(f"Done: {len(trades)} trades across {len(days)} trading days")


if __name__ == "__main__":
    main()
