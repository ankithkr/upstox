"""Estimated per-leg F&O options charges (Upstox + NSE/SEBI schedule, as of 2026).

Rates from Upstox's brokerage calculator and NSE's STT schedule as I know
them - verify against upstox.com/brokerage-charges if they've changed.

STT and stamp duty are charged by transaction DIRECTION, not by whether the
leg is "opening" or "closing": every SELL (selling to open a short, or
selling to close a long early) pays STT on the premium; every BUY (buying
to open a long, or buying back a short early) pays stamp duty instead. The
one exception is actual expiry: a long leg that survives to expiry
in-the-money is auto cash-settled (exercised), which isn't a market sell
and so isn't charged STT on the premium - instead the buyer pays a separate
exercise STT of 0.125% on the INTRINSIC value. A short leg pays no further
charge at expiry either way (worthless or assigned) - that's the cost
retail traders most often forget to model, since it only hits the long side.
"""

BROKERAGE_PER_ORDER = 20.0
STT_SELL_PCT = 0.1  # any sell transaction, on premium value
EXCHANGE_TXN_PCT = 0.0495  # both directions, on premium value
SEBI_PCT = 0.0001  # both directions
STAMP_BUY_PCT = 0.003  # any buy transaction, on premium value
GST_PCT = 18.0  # on brokerage + exchange + SEBI
EXERCISE_STT_PCT = 0.125  # buyer side only, on intrinsic value, if ITM at actual expiry


def _brokerage_exchange_sebi_gst(value: float) -> float:
    brokerage = BROKERAGE_PER_ORDER
    exchange = value * EXCHANGE_TXN_PCT / 100
    sebi = value * SEBI_PCT / 100
    gst = (brokerage + exchange + sebi) * GST_PCT / 100
    return brokerage + exchange + sebi + gst


def sell_transaction_cost(value: float) -> float:
    """Selling to open a short, or selling to close a long early."""
    return _brokerage_exchange_sebi_gst(value) + value * STT_SELL_PCT / 100


def buy_transaction_cost(value: float) -> float:
    """Buying to open a long, or buying back a short early."""
    return _brokerage_exchange_sebi_gst(value) + value * STAMP_BUY_PCT / 100


def exercise_cost(intrinsic_value: float) -> float:
    """Charged to a long leg that finishes in-the-money at actual expiry (cash-settled exercise)."""
    return intrinsic_value * EXERCISE_STT_PCT / 100 if intrinsic_value > 0 else 0.0
