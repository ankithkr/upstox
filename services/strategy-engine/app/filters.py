# Sector index cutoff thresholds, from the strategy PDF section 2.
SECTOR_NEUTRAL_BAND = 0.50  # -0.50% to +0.50% => no trade, insufficient momentum

# Individual stock % change filters, from the strategy PDF section 3.
STOCK_MIN_MOMENTUM = 0.80  # below this magnitude => insufficient momentum, skip
STOCK_IDEAL_MAX = 2.50  # up to this magnitude => ideal momentum zone, valid
STOCK_OVEREXTENDED = 3.00  # at/above this magnitude => overextended, skip

NO_TRADE = "NO_TRADE"
BULLISH = "BULLISH"
BEARISH = "BEARISH"

INSUFFICIENT_MOMENTUM = "INSUFFICIENT_MOMENTUM"
IDEAL_MOMENTUM = "IDEAL_MOMENTUM"
OVEREXTENDED = "OVEREXTENDED"
UNCLASSIFIED = "UNCLASSIFIED"


def classify_sector(pct_change: float) -> str:
    """NO_TRADE / BULLISH / BEARISH, per the sector index cutoff rules."""
    if -SECTOR_NEUTRAL_BAND <= pct_change <= SECTOR_NEUTRAL_BAND:
        return NO_TRADE
    return BULLISH if pct_change > 0 else BEARISH


def classify_stock_momentum(pct_change: float) -> str:
    """INSUFFICIENT_MOMENTUM / IDEAL_MOMENTUM / OVEREXTENDED / UNCLASSIFIED.

    Only IDEAL_MOMENTUM is a valid ORB candidate. UNCLASSIFIED covers the
    2.50%-3.00% band the PDF leaves undefined between "ideal" and
    "overextended" - treated as not tradeable, same as the PDF's other
    unlabeled zones.
    """
    magnitude = abs(pct_change)
    if magnitude < STOCK_MIN_MOMENTUM:
        return INSUFFICIENT_MOMENTUM
    if magnitude <= STOCK_IDEAL_MAX:
        return IDEAL_MOMENTUM
    if magnitude >= STOCK_OVEREXTENDED:
        return OVEREXTENDED
    return UNCLASSIFIED
