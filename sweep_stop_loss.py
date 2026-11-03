"""Sweep candidate stop-loss levels (as a multiple of net credit received)
against NIFTY's real cycle paths, to see which one actually helps.

Uses the two-step engine API so the expensive part (fetching + pricing
every day of every cycle) runs once; each candidate level is then just a
cheap in-memory re-resolution of where each cycle would have exited.
"""

from datetime import date, timedelta
from statistics import mean

from src.options.condor_engine import apply_stop_loss, build_cycle_paths

LOOKBACK_DAYS = 365
SYMBOL = "NIFTY"
CANDIDATES = [None, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0]


def summarize(label: str, results) -> None:
    pnls = [r.pnl for r in results]
    cumulative, peak, max_dd = 0.0, 0.0, 0.0
    for p in pnls:
        cumulative += p
        peak = max(peak, cumulative)
        max_dd = min(max_dd, cumulative - peak)
    n_stopped = sum(1 for r in results if r.stopped_out)
    win_rate = 100 * sum(1 for p in pnls if p > 0) / len(pnls)

    print(
        f"  {label:>10}  total Rs{sum(pnls):>10,.0f}  win% {win_rate:>5.0f}  "
        f"worst Rs{min(pnls):>9,.0f}  maxDD Rs{max_dd:>9,.0f}  stopped {n_stopped:>3}/{len(results)}"
    )


def main() -> None:
    end = date.today()
    start = end - timedelta(days=LOOKBACK_DAYS)
    print(f"Sweeping stop-loss levels on {SYMBOL}, {start} to {end}")

    paths = build_cycle_paths(SYMBOL, start, end)
    print(f"{len(paths)} cycles with complete data\n")

    for mult in CANDIDATES:
        label = "none" if mult is None else f"{mult}x credit"
        results = apply_stop_loss(paths, mult)
        summarize(label, results)


if __name__ == "__main__":
    main()
