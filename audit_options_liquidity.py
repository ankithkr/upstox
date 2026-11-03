"""Audit real NSE options liquidity: index (NIFTY/BANKNIFTY) vs individual
low-volatility stocks, at the OTM strike distances a short-strangle-plus-hedge
(iron condor) would actually use.

Picks low-volatility candidates from the existing liquid-stock universe
(ranked by ATR%, from the equity candle cache already on disk), then compares
real strike-level OI/volume/strike-grid-spacing over the last ~6 months,
sampled once per week, using NSE's free bhavcopy archive.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from statistics import median

from src.backtest.features import DailyIndex
from src.data.universe import LIQUID_UNIVERSE
from src.integrations.candle_cache import read_cached
from src.integrations.nse_bhavcopy import OptionRow, fetch_fo_bhavcopy
from src.integrations.upstox_instruments import build_equity_symbol_index, load_instrument_master

INDEX_CANDIDATES = ["NIFTY", "BANKNIFTY"]
N_LOW_VOL_STOCKS = 6
LOOKBACK_WEEKS = 26  # ~6 months
OTM_PCTS = [0.03, 0.05, 0.08]


def _latest_trading_day() -> tuple[list[OptionRow], date]:
    d = date.today()
    for _ in range(10):
        rows = fetch_fo_bhavcopy(d)
        if rows:
            return rows, d
        d -= timedelta(days=1)
    raise RuntimeError("no F&O bhavcopy found in the last 10 days")


def _sample_dates(weeks: int) -> list[date]:
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    return [monday - timedelta(weeks=w) for w in range(weeks)]


def _bhavcopy_near(d: date, max_lookahead: int = 4) -> tuple[list[OptionRow], date | None]:
    """fetch_fo_bhavcopy for d, or the next few days if d was a holiday/weekend."""
    for offset in range(max_lookahead):
        probe = d + timedelta(days=offset)
        rows = fetch_fo_bhavcopy(probe)
        if rows:
            return rows, probe
    return [], None


def pick_low_vol_stocks(fo_symbols: set[str], n: int) -> list[str]:
    instruments = load_instrument_master()
    symbol_keys = build_equity_symbol_index(instruments)

    candidates = [s for s in LIQUID_UNIVERSE if s in fo_symbols and s in symbol_keys]
    scored = []
    for sym in candidates:
        candles = read_cached(symbol_keys[sym], "days", "1")
        if len(candles) < 40:
            continue
        idx = DailyIndex(candles)
        atr = idx.atr_pct(idx.dates[-1], window=20)
        if atr is not None:
            scored.append((atr, sym))
    scored.sort()
    return [sym for _, sym in scored[:n]]


@dataclass
class StrikeCheck:
    sample_date: date
    underlying: str
    expiry: date
    side: str  # "CALL" or "PUT"
    pct: float
    spot: float
    target_strike: float
    actual_strike: float
    strike_gap_pct: float
    oi: int
    volume: int


def audit_underlying(underlying: str, sample_dates: list[date]) -> list[StrikeCheck]:
    checks: list[StrikeCheck] = []
    for d in sample_dates:
        rows, actual_date = _bhavcopy_near(d)
        if not rows:
            continue
        rows = [r for r in rows if r.symbol == underlying]
        if not rows:
            continue

        nearest_expiry = min(r.expiry for r in rows)
        cycle_rows = [r for r in rows if r.expiry == nearest_expiry]
        spot = next((r.underlying_price for r in cycle_rows if r.underlying_price), None)
        if spot is None:
            continue

        by_type: dict[str, dict[float, OptionRow]] = {"CE": {}, "PE": {}}
        for r in cycle_rows:
            by_type[r.option_type][r.strike] = r

        for pct in OTM_PCTS:
            for side, opt_type, target in (
                ("CALL", "CE", spot * (1 + pct)),
                ("PUT", "PE", spot * (1 - pct)),
            ):
                strikes = by_type[opt_type]
                if not strikes:
                    continue
                actual_strike = min(strikes, key=lambda k: abs(k - target))
                row = strikes[actual_strike]
                checks.append(
                    StrikeCheck(
                        sample_date=actual_date,
                        underlying=underlying,
                        expiry=nearest_expiry,
                        side=side,
                        pct=pct,
                        spot=spot,
                        target_strike=target,
                        actual_strike=actual_strike,
                        strike_gap_pct=100 * abs(actual_strike - target) / spot,
                        oi=row.oi,
                        volume=row.volume,
                    )
                )
    return checks


def summarize(underlying: str, checks: list[StrikeCheck]) -> None:
    if not checks:
        print(f"{underlying}: no data found")
        return

    n_dates = len({c.sample_date for c in checks})
    print(f"\n{underlying}  ({n_dates} sample dates, {len(checks)} strike checks)")
    print(f"  {'OTM%':>6} {'side':>5} {'zero-vol %':>11} {'median OI':>10} {'avg strike gap %':>17}")
    for pct in OTM_PCTS:
        for side in ("CALL", "PUT"):
            subset = [c for c in checks if c.pct == pct and c.side == side]
            if not subset:
                continue
            zero_vol_pct = 100 * sum(1 for c in subset if c.volume == 0) / len(subset)
            med_oi = median(c.oi for c in subset)
            avg_gap = sum(c.strike_gap_pct for c in subset) / len(subset)
            print(f"  {pct*100:>5.0f}% {side:>5} {zero_vol_pct:>10.0f}% {med_oi:>10,.0f} {avg_gap:>16.2f}%")


def main() -> None:
    latest_rows, latest_date = _latest_trading_day()
    print(f"Latest bhavcopy available: {latest_date}")
    fo_symbols = {r.symbol for r in latest_rows if r.underlying_type == "STOCK"}

    low_vol_stocks = pick_low_vol_stocks(fo_symbols, N_LOW_VOL_STOCKS)
    print(f"Low-volatility stock candidates (lowest ATR%% in LIQUID_UNIVERSE, F&O-enabled): {low_vol_stocks}")

    sample_dates = _sample_dates(LOOKBACK_WEEKS)
    print(f"Sampling {len(sample_dates)} weekly dates from {sample_dates[-1]} to {sample_dates[0]}")

    for underlying in INDEX_CANDIDATES + low_vol_stocks:
        checks = audit_underlying(underlying, sample_dates)
        summarize(underlying, checks)


if __name__ == "__main__":
    main()
