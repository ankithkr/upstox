"""Summary tables over a list of backtest trades (see snapshots.taken_trades).

`net_r` (R multiple after costs) is the number that matters; the win
rate here is the share of trades that hit their target, which with a
breakeven stop and a 3R target is well below the share that made money.
"""

from collections import defaultdict

from src.backtest.orb_engine import EOD_EXIT, STOPPED_BREAKEVEN, STOPPED_LOSS, TARGET_HIT

OUTCOME_ORDER = [TARGET_HIT, STOPPED_BREAKEVEN, STOPPED_LOSS, EOD_EXIT]


def overview(trades: list[dict], start_date, end_date, trading_days_count: int, gate_open_days: int = 0) -> dict:
    unique = {(t["date"], t["symbol"], t["direction"]) for t in trades}
    return {
        "start_date": str(start_date),
        "end_date": str(end_date),
        "trading_days": trading_days_count,
        "gate_open_days": gate_open_days,
        "days_traded": len({t["date"] for t in trades}),
        "total_signals": len(trades),
        "unique_signals": len(unique),
    }


def outcome_breakdown(trades: list[dict]) -> list[tuple]:
    counts = defaultdict(int)
    for t in trades:
        counts[t["outcome"]] += 1
    total = len(trades) or 1
    return [
        (outcome, counts.get(outcome, 0), round(100 * counts.get(outcome, 0) / total, 1))
        for outcome in OUTCOME_ORDER
    ]


def key_metrics(trades: list[dict]) -> dict:
    total = len(trades) or 1
    target_hits = [t for t in trades if t["outcome"] == TARGET_HIT]
    stopped_losses = [t for t in trades if t["outcome"] == STOPPED_LOSS]
    net = [_net(t) for t in trades]
    gains, losses = sum(x for x in net if x > 0), -sum(x for x in net if x < 0)

    return {
        "win_rate_pct": round(100 * len(target_hits) / total, 1),
        "profitable_pct": round(100 * sum(1 for x in net if x > 0) / total, 1),
        "avg_net_r": round(sum(net) / total, 3),
        "total_net_r": round(sum(net), 1),
        "avg_gross_r": _avg(t["r_multiple"] for t in trades if "r_multiple" in t),
        "profit_factor": round(gains / losses, 2) if losses else None,
        "max_drawdown_r": round(_max_drawdown(trades), 1),
        "avg_stop_pct": _avg(t["risk_pct"] for t in trades if "risk_pct" in t),
        "cost_pct": trades[0].get("cost_pct") if trades else None,
        "avg_hold_minutes": _avg(t["hold_minutes"] for t in trades),
        "avg_hold_minutes_target_hit": _avg(t["hold_minutes"] for t in target_hits),
        "avg_hold_minutes_stopped_loss": _avg(t["hold_minutes"] for t in stopped_losses),
    }


def equity_curve(trades: list[dict]) -> list[list]:
    """Cumulative net R by trading day (only days with trades)."""
    by_day = defaultdict(float)
    for t in trades:
        by_day[t["date"]] += _net(t)
    total, curve = 0.0, []
    for day in sorted(by_day):
        total += by_day[day]
        curve.append([day, round(total, 2)])
    return curve


def by_year(trades: list[dict]) -> list[tuple]:
    return _grouped(trades, key=lambda t: t["date"][:4], sort_by_count=False)


def by_month(trades: list[dict]) -> list[tuple]:
    return _grouped(trades, key=lambda t: t["date"][:7], sort_by_count=False)


def by_sector(trades: list[dict]) -> list[tuple]:
    return _grouped(trades, key=lambda t: t["sector"], sort_by_count=True)


def by_direction(trades: list[dict]) -> list[tuple]:
    return _grouped(trades, key=lambda t: t["direction"], sort_by_count=False)


def _net(t: dict) -> float:
    return t["net_r"] if "net_r" in t else t.get("r_multiple", 0.0)


def _max_drawdown(trades: list[dict]) -> float:
    peak = equity = drawdown = 0.0
    for _day, cumulative in equity_curve(trades):
        equity = cumulative
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def _grouped(trades, key, sort_by_count) -> list[tuple]:
    groups = defaultdict(list)
    for t in trades:
        groups[key(t)].append(t)

    labels = sorted(groups, key=lambda label: -len(groups[label])) if sort_by_count else sorted(groups)
    return [_group_row(label, groups[label]) for label in labels]


def _group_row(label, group_trades) -> tuple:
    """(label, trades, target hits, target-hit %, net R total, net R per trade)"""
    total = len(group_trades)
    target_hits = sum(1 for t in group_trades if t["outcome"] == TARGET_HIT)
    win_rate = round(100 * target_hits / total, 1) if total else 0
    net = sum(_net(t) for t in group_trades)
    return (label, total, target_hits, win_rate, round(net, 1), round(net / total, 3) if total else 0)


def _avg(values) -> float:
    values = list(values)
    return round(sum(values) / len(values), 3) if values else 0
