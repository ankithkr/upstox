"""The v2 strategy's tunable rules, in one place.

Defaults are the configuration validated on 2023-01 -> 2026-08 data
(see research2.py / exp5-8): a 30-minute opening-range breakout, taken
only in a calm, trending market and only on volume. Every field is a
plain number so the same object drives the backtest, the review UI and
(later) the paper-trading engine.
"""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class StrategyParams:
    # --- market regime gate (the single biggest profitability lever) ---
    nifty_band_pct: float = 0.30  # |NIFTY 09:30 move| must exceed this to pick a side
    max_vix: float = 14.0  # skip the day if previous-close India VIX is at/above this
    min_nifty_trend_pct: float = 0.0  # NIFTY prev close vs its 20-day mean, signed with the trade, must exceed this
    # --- top-down selection ---
    sector_band_pct: float = 0.50  # sector 09:30 move must exceed this (in the trade direction)
    top_sectors: int = 3
    stock_min_move_pct: float = 0.80  # stock 09:30 move, in the trade direction
    stock_max_move_pct: float = 2.50  # above this = overextended
    min_opening_volume_ratio: float = 1.0  # 09:15-09:30 volume vs the same window's 20-day average
    # --- entry ---
    opening_range_candles: int = 6  # 5-min candles: 6 => range is 09:15-09:45, breakouts from 09:45
    min_breakout_volume_ratio: float = 1.5  # breakout candle volume vs same time slot's 20-day average
    # --- risk / exit ---
    stop_floor_atr: float = 0.40  # stop is at least this multiple of 14-day ATR% away from entry
    breakeven_rrr: float | None = 1.5  # move stop to entry once price reaches this multiple of risk
    target_rrr: float = 3.0
    # --- portfolio / realism ---
    max_trades_per_day: int = 3
    cost_notional: float = 50_000.0  # position value used only to turn Rs brokerage into % of price
    brokerage_per_order: float = 12.5
    slippage_pct: float = 0.03  # round-trip, % of price

    def as_dict(self) -> dict:
        return asdict(self)


DEFAULT_PARAMS = StrategyParams()


def describe(p: StrategyParams = DEFAULT_PARAMS) -> list[dict]:
    """Human-readable rules, generated from the parameters so the UI never drifts from the code."""
    be = f"move the stop to entry once price reaches {p.breakeven_rrr:g}R" if p.breakeven_rrr else "no breakeven move"
    return [
        {"title": "1. Market regime gate", "text": (
            f"NIFTY 50's move at 09:30 (vs previous close) must exceed ±{p.nifty_band_pct:g}% - it picks the side: "
            f"up = long only, down = short only. The previous close of India VIX must be below {p.max_vix:g}, and NIFTY's "
            f"previous close must sit on the right side of its 20-day average (above for longs, below for shorts"
            f"{'' if p.min_nifty_trend_pct == 0 else f', by more than {p.min_nifty_trend_pct:g}%'}). "
            "If any check fails the whole day is skipped. This gate is what makes the strategy profitable.")},
        {"title": "2. Sectors", "text": (
            f"Among the liquid sector indices, take the {p.top_sectors} strongest (for longs) or weakest (for shorts) at 09:30, "
            f"each moving more than {p.sector_band_pct:g}% in the trade direction.")},
        {"title": "3. Stocks", "text": (
            f"Constituents of those sectors, from the 120 most-traded stocks, that moved {p.stock_min_move_pct:g}%-"
            f"{p.stock_max_move_pct:g}% in the trade direction at 09:30 (bigger = overextended), with opening volume "
            f"(09:15-09:30) at least {p.min_opening_volume_ratio:g}× the stock's 20-day norm. A stock in several sectors counts once.")},
        {"title": "4. Entry", "text": (
            f"Opening range = high/low of the first {p.opening_range_candles} five-minute candles "
            f"(09:15-{9 + (15 + 5 * p.opening_range_candles) // 60:02d}:{(15 + 5 * p.opening_range_candles) % 60:02d}). A 5-minute candle must "
            f"close beyond it; entry is then a stop order at that candle's high (long) / low (short). The breakout candle's volume must be at "
            f"least {p.min_breakout_volume_ratio:g}× the same time slot's 20-day norm, otherwise the trade is skipped.")},
        {"title": "5. Stop and exit", "text": (
            f"Stop just beyond the breakout candle's far end, but never closer than {p.stop_floor_atr:g}× the stock's 14-day ATR "
            f"(tiny stops are eaten by costs). Target {p.target_rrr:g}R; {be}; any open position is closed at 15:15.")},
        {"title": "6. Portfolio limit and costs", "text": (
            f"At most {p.max_trades_per_day} trades per day (first entries win). Results are shown in R (multiples of the risk taken) "
            f"after costs: Rs {p.brokerage_per_order:g} per order brokerage (assuming ~Rs {p.cost_notional:,.0f} positions), STT, exchange "
            f"charges, GST, stamp duty and {p.slippage_pct:g}% slippage. No capital or position sizing is modelled.")},
    ]
