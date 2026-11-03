"""Estimated Upstox equity-intraday charges for one round trip.

These rates are ESTIMATES from Upstox/NSE's published schedule as I know
it - verify against upstox.com/brokerage-charges and edit the constants
if they've changed. Every trade's `charges` column comes from here.
"""

BROKERAGE_FLAT = 20.0  # per executed order ...
BROKERAGE_PCT_CAP = 0.1  # ... or this % of the order value, whichever is lower
STT_SELL_PCT = 0.025  # sell side only
EXCHANGE_TXN_PCT = 0.00297  # NSE, both sides
SEBI_PCT = 0.0001  # both sides
STAMP_BUY_PCT = 0.003  # buy side only
GST_PCT = 18.0  # on brokerage + exchange + SEBI


def round_trip_charges(direction: str, qty: int, entry_price: float, exit_price: float) -> float:
    """Total charges for opening and closing `qty` shares (LONG buys first, SHORT sells first)."""
    if direction == "LONG":
        buy_value, sell_value = qty * entry_price, qty * exit_price
    else:
        buy_value, sell_value = qty * exit_price, qty * entry_price

    brokerage = sum(min(BROKERAGE_FLAT, v * BROKERAGE_PCT_CAP / 100) for v in (buy_value, sell_value))
    turnover = buy_value + sell_value
    exchange = turnover * EXCHANGE_TXN_PCT / 100
    sebi = turnover * SEBI_PCT / 100
    stt = sell_value * STT_SELL_PCT / 100
    stamp = buy_value * STAMP_BUY_PCT / 100
    gst = (brokerage + exchange + sebi) * GST_PCT / 100
    return round(brokerage + exchange + sebi + stt + stamp + gst, 2)
