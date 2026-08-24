from collections import defaultdict

from src.backtest.orb_engine import EOD_EXIT, STOPPED_BREAKEVEN, STOPPED_LOSS, TARGET_HIT

OUTCOME_ORDER = [TARGET_HIT, STOPPED_BREAKEVEN, STOPPED_LOSS, EOD_EXIT]


def overview(trades: list[dict], start_date, end_date, trading_days_count: int) -> dict:
    unique = {(t["date"], t["symbol"], t["direction"]) for t in trades}
    return {
        "start_date": str(start_date),
        "end_date": str(end_date),
        "trading_days": trading_days_count,
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

    return {
        "win_rate_pct": round(100 * len(target_hits) / total, 1),
        "avg_hold_minutes": _avg(t["hold_minutes"] for t in trades),
        "avg_hold_minutes_target_hit": _avg(t["hold_minutes"] for t in target_hits),
        "avg_hold_minutes_stopped_loss": _avg(t["hold_minutes"] for t in stopped_losses),
    }


def by_month(trades: list[dict]) -> list[tuple]:
    return _grouped(trades, key=lambda t: t["date"][:7], sort_by_count=False)


def by_sector(trades: list[dict]) -> list[tuple]:
    return _grouped(trades, key=lambda t: t["sector"], sort_by_count=True)


def by_direction(trades: list[dict]) -> list[tuple]:
    return _grouped(trades, key=lambda t: t["direction"], sort_by_count=False)


def _grouped(trades, key, sort_by_count) -> list[tuple]:
    groups = defaultdict(list)
    for t in trades:
        groups[key(t)].append(t)

    labels = sorted(groups, key=lambda label: -len(groups[label])) if sort_by_count else sorted(groups)
    return [_group_row(label, groups[label]) for label in labels]


def _group_row(label, group_trades) -> tuple:
    total = len(group_trades)
    target_hits = sum(1 for t in group_trades if t["outcome"] == TARGET_HIT)
    win_rate = round(100 * target_hits / total, 1) if total else 0
    return (label, total, target_hits, win_rate)


def _avg(values) -> float:
    values = list(values)
    return round(sum(values) / len(values), 1) if values else 0
