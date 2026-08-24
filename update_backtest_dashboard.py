"""Run the top-down ORB backtest and write results to Google Sheets.

'Backtest dahboard' (sheet 1, renamed by hand) gets the summary
tables; 'Backtest Trades' gets the raw list of every triggered entry.
Rerunning refreshes both in place.
"""

from datetime import date, timedelta

from src.backtest import dashboard
from src.backtest.reference_values import trading_days
from src.backtest.runner import run_backtest
from src.data.indices import NIFTY_50_INSTRUMENT_KEY
from src.integrations.google_sheets import get_or_create_worksheet, get_spreadsheet
from src.integrations.upstox_history import get_candles

DASHBOARD_SHEET = "Backtest dahboard"  # matches the sheet name as renamed in the spreadsheet
TRADES_SHEET = "Backtest Trades"
BACKTEST_MONTHS_BACK = 182  # ~6 months

TRADE_COLUMNS = [
    "date",
    "sector",
    "symbol",
    "direction",
    "market_bias",
    "sector_change",
    "stock_change",
    "breakout_time",
    "entry_time",
    "entry_price",
    "stop_loss",
    "target",
    "outcome",
    "exit_time",
    "exit_price",
    "hold_minutes",
    "achieved_1_2_by_close",
]


def _latest_trading_day() -> date:
    today = date.today()
    candles = get_candles(NIFTY_50_INSTRUMENT_KEY, "days", "1", today - timedelta(days=14), today)
    if not candles:
        raise RuntimeError("No recent NIFTY 50 daily candles found to anchor the backtest end date")
    return date.fromisoformat(candles[-1][0][:10])


def write_trades_sheet(spreadsheet, trades: list[dict]):
    worksheet = get_or_create_worksheet(
        spreadsheet, TRADES_SHEET, rows=len(trades) + 1, cols=len(TRADE_COLUMNS)
    )
    worksheet.clear()
    rows = [TRADE_COLUMNS] + [[t.get(c) for c in TRADE_COLUMNS] for t in trades]
    worksheet.update(values=rows, range_name="A1")
    return worksheet


def write_dashboard_sheet(spreadsheet, trades: list[dict], start_date, end_date, days_count):
    worksheet = spreadsheet.worksheet(DASHBOARD_SHEET)
    worksheet.clear()

    ov = dashboard.overview(trades, start_date, end_date, days_count)
    metrics = dashboard.key_metrics(trades)

    rows = [
        ["Backtest Dashboard"],
        [],
        ["Period", f"{ov['start_date']} to {ov['end_date']}"],
        ["Trading days", ov["trading_days"]],
        ["Total signals", ov["total_signals"]],
        ["Unique signals (date + symbol + direction)", ov["unique_signals"]],
        [],
        ["Win rate (target hit by close)", f"{metrics['win_rate_pct']}%"],
        ["Avg hold time - all trades (min)", metrics["avg_hold_minutes"]],
        ["Avg hold time - target hit (min)", metrics["avg_hold_minutes_target_hit"]],
        ["Avg hold time - stopped loss (min)", metrics["avg_hold_minutes_stopped_loss"]],
        [],
        ["Outcome", "Count", "% of total"],
        *[list(r) for r in dashboard.outcome_breakdown(trades)],
        [],
        ["Month", "Trades", "Target Hit", "Win Rate %"],
        *[list(r) for r in dashboard.by_month(trades)],
        [],
        ["Sector", "Trades", "Target Hit", "Win Rate %"],
        *[list(r) for r in dashboard.by_sector(trades)],
        [],
        ["Direction", "Trades", "Target Hit", "Win Rate %"],
        *[list(r) for r in dashboard.by_direction(trades)],
    ]

    worksheet.update(values=rows, range_name="A1")
    return worksheet


def main():
    spreadsheet = get_spreadsheet()

    end_date = _latest_trading_day()
    start_date = end_date - timedelta(days=BACKTEST_MONTHS_BACK)

    print(f"Running backtest: {start_date} to {end_date}...")
    trades = run_backtest(start_date, end_date)

    nifty_15m = get_candles(NIFTY_50_INSTRUMENT_KEY, "minutes", "15", start_date, end_date)
    days_count = len(trading_days(nifty_15m))

    write_trades_sheet(spreadsheet, trades)
    write_dashboard_sheet(spreadsheet, trades, start_date, end_date, days_count)

    print(f"Done: {len(trades)} signals across {days_count} trading days")


if __name__ == "__main__":
    main()
