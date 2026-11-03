"""Backtest the short-strangle-plus-hedge (iron condor) idea on NIFTY,
BANKNIFTY, and a handful of low-volatility F&O stocks, over the last N
months, with a stop-loss chosen from sweep_stop_loss.py's sweep of NIFTY's
own historical cycle paths (2.0x the net credit received - see that
script's output for why: tighter stops made both total P&L and drawdown
worse in-sample, a known whipsaw effect for premium-selling strategies).

Strikes are picked fresh each cycle off the underlying's own recent
realized volatility (see src/options/strikes.py). Entry prices are NSE's
own settle price; exits are either the stop-loss trigger day or actual
expiry - see src/options/condor_engine.py and src/options/costs.py.
"""

from datetime import date, timedelta
from statistics import mean

from audit_options_liquidity import _latest_trading_day, pick_low_vol_stocks
from src.options.condor_engine import CycleResult, run_condor_backtest

LOOKBACK_DAYS = 365
INDEX_SYMBOLS = ["NIFTY", "BANKNIFTY"]
N_STOCKS = 6
K_SHORT = 1.0
K_WING = 1.0
STOP_LOSS_MULT = 2.0


def summarize(symbol: str, results: list[CycleResult]) -> None:
    if not results:
        print(f"\n{symbol}: no completed cycles found")
        return

    pnls = [r.pnl for r in results]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    cumulative, peak, max_dd = 0.0, 0.0, 0.0
    for p in pnls:
        cumulative += p
        peak = max(peak, cumulative)
        max_dd = min(max_dd, cumulative - peak)
    n_stopped = sum(1 for r in results if r.stopped_out)

    print(f"\n{symbol}  ({len(results)} cycles, {results[0].entry_date} to {results[-1].expiry_date})")
    print(f"  total P&L:        Rs {sum(pnls):>12,.0f}")
    print(f"  avg P&L/cycle:    Rs {mean(pnls):>12,.0f}")
    print(f"  win rate:          {100 * len(wins) / len(results):>11.0f}%")
    print(f"  avg win:          Rs {mean(wins) if wins else 0:>12,.0f}")
    print(f"  avg loss:         Rs {mean(losses) if losses else 0:>12,.0f}")
    print(f"  worst cycle:      Rs {min(pnls):>12,.0f}")
    print(f"  max drawdown:     Rs {max_dd:>12,.0f}")
    print(f"  avg net credit:   Rs {mean(r.net_credit for r in results):>12,.0f}")
    print(f"  avg costs/cycle:  Rs {mean(r.costs for r in results):>12,.0f}")
    print(f"  stopped out:       {n_stopped}/{len(results)}")


def main() -> None:
    end = date.today()
    start = end - timedelta(days=LOOKBACK_DAYS)
    print(f"Backtesting {start} to {end}  (k_short={K_SHORT}, k_wing={K_WING}, stop_loss={STOP_LOSS_MULT}x credit)")

    latest_rows, _ = _latest_trading_day()
    fo_symbols = {r.symbol for r in latest_rows if r.underlying_type == "STOCK"}
    stocks = pick_low_vol_stocks(fo_symbols, N_STOCKS)
    print(f"Low-volatility stock candidates: {stocks}")

    for symbol in INDEX_SYMBOLS + stocks:
        results = run_condor_backtest(
            symbol, start, end, k_short=K_SHORT, k_wing=K_WING, stop_loss_mult=STOP_LOSS_MULT
        )
        summarize(symbol, results)


if __name__ == "__main__":
    main()
