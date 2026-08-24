from src.strategy.filters import BEARISH, BULLISH

NEUTRAL = "NEUTRAL"

# Overall market bias, from NIFTY 50's % change (not in the original
# strategy PDF — added separately). Below the bearish threshold and
# above the bullish one lies the neutral band: broad market is
# sideways, raising the risk of false breakouts across all sectors.
NIFTY_BULLISH_THRESHOLD = 0.30
NIFTY_BEARISH_THRESHOLD = -0.30


def get_market_bias(nifty_pct_change: float) -> str:
    """Overall market bias from NIFTY 50's % change.

    > +0.30%: bullish — only take longs in bullish sectors.
    < -0.30%: bearish — only take shorts in bearish sectors.
    otherwise: neutral — sideways market, skip new setups.
    """
    if nifty_pct_change > NIFTY_BULLISH_THRESHOLD:
        return BULLISH
    if nifty_pct_change < NIFTY_BEARISH_THRESHOLD:
        return BEARISH
    return NEUTRAL
