from src.strategy.filters import BEARISH, BULLISH, classify_sector
from src.strategy.market_bias import NEUTRAL

DEFAULT_TOP_N = 2


def select_sectors(
    sector_changes: dict[str, float], market_bias: str, top_n: int = DEFAULT_TOP_N
) -> list[str]:
    """The top 1-2 strongest/weakest sectors, per the top-down selection rules.

    Only sectors matching the overall market bias are eligible: bullish
    sectors when the market is bullish, bearish sectors when bearish. A
    neutral market bias yields no sectors at all - the whole day is
    skipped, per the missed NIFTY 50 bias rule.
    """
    if market_bias == NEUTRAL:
        return []

    wanted_classification = BULLISH if market_bias == BULLISH else BEARISH
    eligible = {
        name: change
        for name, change in sector_changes.items()
        if classify_sector(change) == wanted_classification
    }

    ranked = sorted(eligible, key=lambda name: eligible[name], reverse=(market_bias == BULLISH))
    return ranked[:top_n]
