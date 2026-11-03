"""Compare three ways of running the condor over an extended (2-3yr)
history: hold-to-expiry baseline, the 2.0x-credit stop-loss, and the
roll-the-tested-side defensive adjustment - see condor_engine.py for how
each works.
"""

from datetime import date, timedelta
from statistics import mean

from src.options.condor_engine import AdjustedCycleResult, CycleResult, run_condor_backtest, run_condor_with_rolls

LOOKBACK_DAYS = 365 * 3
SYMBOLS = ["NIFTY", "BANKNIFTY"]
STOP_LOSS_MULT = 2.0


def _drawdown(pnls: list[float]) -> float:
    cumulative, peak, max_dd = 0.0, 0.0, 0.0
    for p in pnls:
        cumulative += p
        peak = max(peak, cumulative)
        max_dd = min(max_dd, cumulative - peak)
    return max_dd


def summarize(label: str, pnls: list[float]) -> None:
    if not pnls:
        print(f"  {label:>14}: no cycles")
        return
    win_rate = 100 * sum(1 for p in pnls if p > 0) / len(pnls)
    print(
        f"  {label:>14}  n={len(pnls):>4}  total Rs{sum(pnls):>10,.0f}  "
        f"avg Rs{mean(pnls):>8,.0f}  win% {win_rate:>5.0f}  "
        f"worst Rs{min(pnls):>9,.0f}  maxDD Rs{_drawdown(pnls):>9,.0f}"
    )


def main() -> None:
    end = date.today()
    start = end - timedelta(days=LOOKBACK_DAYS)
    print(f"Comparing over {start} to {end} ({LOOKBACK_DAYS / 365:.1f} years)\n")

    for symbol in SYMBOLS:
        print(f"{symbol}")
        baseline: list[CycleResult] = run_condor_backtest(symbol, start, end, stop_loss_mult=None)
        summarize("hold-to-expiry", [r.pnl for r in baseline])

        stopped: list[CycleResult] = run_condor_backtest(symbol, start, end, stop_loss_mult=STOP_LOSS_MULT)
        summarize(f"{STOP_LOSS_MULT}x stop-loss", [r.pnl for r in stopped])

        rolled: list[AdjustedCycleResult] = run_condor_with_rolls(symbol, start, end)
        summarize("rolled", [r.pnl for r in rolled])

        n_with_roll = sum(1 for r in rolled if r.n_rolls > 0)
        total_rolls = sum(r.n_rolls for r in rolled)
        print(f"  -> {total_rolls} rolls across {n_with_roll}/{len(rolled)} cycles " f"({mean(r.n_rolls for r in rolled):.2f} avg)")
        print()


if __name__ == "__main__":
    main()
