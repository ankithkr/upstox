"""Estimated Upstox equity-intraday round-trip charges.

Same schedule as src/paper/charges.py (ESTIMATES - verify against
upstox.com/brokerage-charges); kept as its own copy so this package has no
dependency on the paper-trading module.
"""

BROKERAGE_FLAT = 20.0
BROKERAGE_PCT_CAP = 0.1
STT_SELL_PCT = 0.025
EXCHANGE_TXN_PCT = 0.00297
SEBI_PCT = 0.0001
STAMP_BUY_PCT = 0.003
GST_PCT = 18.0


def round_trip_charges(side: str, qty: int, entry: float, exit_: float) -> float:
    buy, sell = (qty * entry, qty * exit_) if side == "LONG" else (qty * exit_, qty * entry)
    brokerage = sum(min(BROKERAGE_FLAT, v * BROKERAGE_PCT_CAP / 100) for v in (buy, sell))
    turnover = buy + sell
    exchange = turnover * EXCHANGE_TXN_PCT / 100
    sebi = turnover * SEBI_PCT / 100
    stt = sell * STT_SELL_PCT / 100
    stamp = buy * STAMP_BUY_PCT / 100
    gst = (brokerage + exchange + sebi) * GST_PCT / 100
    return brokerage + exchange + sebi + stt + stamp + gst
