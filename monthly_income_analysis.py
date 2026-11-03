"""What would this NIFTY condor (with the 2.0x-credit stop-loss) actually
look like as a monthly income stream on Rs 1L / Rs 2L of capital?

Capital-at-risk per "1x condor" (1 lot of all 4 legs) is estimated as the
structure's own defined max loss - wing width in points, times lot size,
minus the net credit collected. That's a reasonable floor for how much
capital a position can absorb before being wiped out; real broker SPAN+
exposure margin can differ (usually not far off for a defined-risk spread,
but verify with Upstox's own margin calculator before sizing real money).

Cycle P&L is booked to the calendar month it actually exits in, then
summed per month, so "monthly income" means what it actually would in a
trading account - several cycles can land in the same month.
"""

from collections import defaultdict
from datetime import date, timedelta
from statistics import mean, median, stdev

from src.options.condor_engine import CycleResult, run_condor_backtest

SYMBOL = "NIFTY"
LOOKBACK_DAYS = 365 * 3
STOP_LOSS_MULT = 2.0
CAPITAL_LEVELS = [100_000, 200_000]


def max_loss_per_condor(r: CycleResult) -> float:
    wing_width = min(
        r.strikes["hedge_call"] - r.strikes["short_call"],
        r.strikes["short_put"] - r.strikes["hedge_put"],
    )
    return wing_width * r.lot_size - r.net_credit


def monthly_series(results: list[CycleResult]) -> dict[str, float]:
    by_month: dict[str, float] = defaultdict(float)
    for r in results:
        by_month[r.exit_date.strftime("%Y-%m")] += r.pnl
    return dict(sorted(by_month.items()))


def print_stats(label: str, months: dict[str, float]) -> None:
    values = list(months.values())
    cumulative, peak, max_dd = 0.0, 0.0, 0.0
    for v in values:
        cumulative += v
        peak = max(peak, cumulative)
        max_dd = min(max_dd, cumulative - peak)
    profitable = sum(1 for v in values if v > 0)

    print(f"\n{label}")
    print(f"  months:            {len(values)}")
    print(f"  avg monthly P&L:   Rs {mean(values):>10,.0f}")
    print(f"  median monthly:    Rs {median(values):>10,.0f}")
    print(f"  std dev monthly:   Rs {stdev(values):>10,.0f}")
    print(f"  best month:        Rs {max(values):>10,.0f}")
    print(f"  worst month:       Rs {min(values):>10,.0f}")
    print(f"  profitable months:  {profitable}/{len(values)}  ({100 * profitable / len(values):.0f}%)")
    print(f"  max drawdown:      Rs {max_dd:>10,.0f}")
    print(f"  total over period: Rs {sum(values):>10,.0f}")


def main() -> None:
    end = date.today()
    start = end - timedelta(days=LOOKBACK_DAYS)
    print(f"{SYMBOL}, {start} to {end}, stop-loss={STOP_LOSS_MULT}x credit\n")

    results = run_condor_backtest(SYMBOL, start, end, stop_loss_mult=STOP_LOSS_MULT)
    print(f"{len(results)} completed cycles")

    max_losses = [max_loss_per_condor(r) for r in results]
    avg_risk = mean(max_losses)
    worst_risk = max(max_losses)
    print(f"capital-at-risk per 1x condor: avg Rs {avg_risk:,.0f}, worst-seen Rs {worst_risk:,.0f}")

    base_months = monthly_series(results)
    print_stats("1x condor (base case, 1 lot per leg)", base_months)

    for capital in CAPITAL_LEVELS:
        for basis_name, basis_risk in (("avg-risk sizing", avg_risk), ("worst-case sizing", worst_risk)):
            n = max(int(capital // basis_risk), 0)
            print(f"\n--- Capital Rs {capital:,} | {basis_name}: {n} condor(s) at a time ---")
            if n == 0:
                print("  capital too small for even 1 condor at this sizing basis")
                continue
            scaled = {m: v * n for m, v in base_months.items()}
            print_stats(f"Rs {capital:,} capital, {n}x condor", scaled)


if __name__ == "__main__":
    main()
