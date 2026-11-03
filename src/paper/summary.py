from collections import defaultdict

from src.paper.engine import CLOSED, OPEN, SKIPPED


def _num(value) -> float:
    return float(value) if value not in (None, "") else 0.0


def account_summary(trades: list[dict], starting_capital: float) -> dict:
    """Account-level numbers from every trade ever recorded."""
    taken = [t for t in trades if t["status"] in (OPEN, CLOSED)]
    closed = [t for t in taken if t["status"] == CLOSED]
    open_ = [t for t in taken if t["status"] == OPEN]

    realised = sum(_num(t["net_pnl"]) for t in closed)
    unrealised = sum(_num(t["net_pnl"]) for t in open_)
    wins = [t for t in closed if _num(t["net_pnl"]) > 0]

    return {
        "starting_capital": starting_capital,
        "equity": round(starting_capital + realised + unrealised, 2),
        "realised_net_pnl": round(realised, 2),
        "unrealised_net_pnl": round(unrealised, 2),
        "return_pct": round(100 * (realised + unrealised) / starting_capital, 2),
        "closed_trades": len(closed),
        "open_trades": len(open_),
        "skipped_signals": sum(1 for t in trades if t["status"] == SKIPPED),
        "win_rate_pct": round(100 * len(wins) / len(closed), 1) if closed else 0,
        "gross_pnl": round(sum(_num(t["gross_pnl"]) for t in closed), 2),
        "total_charges": round(sum(_num(t["charges"]) for t in closed), 2),
    }


def daily_table(trades: list[dict], starting_capital: float) -> list[list]:
    """One row per trading day: trades, wins, gross, charges, net, end-of-day equity."""
    by_day = defaultdict(list)
    for t in trades:
        if t["status"] in (OPEN, CLOSED):
            by_day[t["date"]].append(t)

    rows, equity = [], starting_capital
    for day in sorted(by_day):
        day_trades = by_day[day]
        net = sum(_num(t["net_pnl"]) for t in day_trades)
        equity += net
        rows.append(
            [
                day,
                len(day_trades),
                sum(1 for t in day_trades if _num(t["net_pnl"]) > 0),
                round(sum(_num(t["gross_pnl"]) for t in day_trades), 2),
                round(sum(_num(t["charges"]) for t in day_trades), 2),
                round(net, 2),
                round(equity, 2),
            ]
        )
    return rows


DAILY_HEADER = ["Date", "Trades", "Winners", "Gross P&L", "Charges", "Net P&L", "Equity"]


def closed_pnl_before(trades: list[dict], day: str) -> float:
    """Realised net P&L from all closed trades on days before `day`."""
    return sum(_num(t["net_pnl"]) for t in trades if t["status"] == CLOSED and t["date"] < day)
