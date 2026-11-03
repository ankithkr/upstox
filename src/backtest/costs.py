"""Round-trip trading costs for an intraday equity (MIS) trade, as % of price."""

STT_SELL_PCT = 0.025  # intraday: on the sell side only
EXCHANGE_PCT_PER_LEG = 0.00297  # NSE transaction charge
GST = 1.18  # on brokerage + exchange charges
STAMP_BUY_PCT = 0.003


def round_trip_cost_pct(notional: float, brokerage_per_order: float, slippage_pct: float) -> float:
    brokerage = 2 * brokerage_per_order * GST / notional * 100
    return brokerage + STT_SELL_PCT + 2 * EXCHANGE_PCT_PER_LEG * GST + STAMP_BUY_PCT + slippage_pct


def net_r_multiple(r_multiple: float, risk_pct: float, cost_pct: float) -> float:
    """R after costs: a cost of `cost_pct` of price is `cost_pct / risk_pct` of the risk taken."""
    return r_multiple - cost_pct / risk_pct
