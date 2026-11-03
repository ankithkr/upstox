"""Volatility-scaled strike selection for a short-strangle-plus-hedge (iron condor).

The short strikes sit `k_short` expected-moves-to-expiry away from spot on
each side - "where the underlying isn't expected to go" as a statistical
band sized off its own recent volatility, not a flat % that's the same in a
calm week and a choppy one, and not the same for a 5-day weekly cycle as for
a ~21-day monthly one. The hedge sits another `k_wing` of that same band
further out, so the condor automatically widens in choppier regimes (and
tightens, collecting less but safer premium, in calm ones).
"""

from math import sqrt


def expected_move_pct(atr_pct_daily: float, trading_days_to_expiry: int) -> float:
    """Scale a daily ATR% to an expected move over `trading_days_to_expiry` sessions.

    ATR doesn't compound the way return variance does, but sqrt(time)
    scaling is the standard rough-and-ready way to stretch a daily
    volatility estimate to a multi-day horizon, and it's what keeps a
    5-day weekly cycle and a ~21-day monthly one on a comparable footing.
    """
    return atr_pct_daily * sqrt(trading_days_to_expiry)


def _nearest(strikes: list[float], target: float) -> float:
    return min(strikes, key=lambda k: abs(k - target))


def condor_strikes(
    spot: float,
    call_strikes: list[float],
    put_strikes: list[float],
    move_pct: float,
    k_short: float = 1.0,
    k_wing: float = 1.0,
) -> dict[str, float]:
    """Short call/put + hedge call/put strikes, nearest-available to the vol-scaled targets."""
    short_dist = k_short * move_pct / 100 * spot
    wing_dist = k_wing * move_pct / 100 * spot

    short_call = _nearest(call_strikes, spot + short_dist)
    short_put = _nearest(put_strikes, spot - short_dist)

    call_beyond = [s for s in call_strikes if s > short_call] or call_strikes
    put_beyond = [s for s in put_strikes if s < short_put] or put_strikes
    hedge_call = _nearest(call_beyond, spot + short_dist + wing_dist)
    hedge_put = _nearest(put_beyond, spot - short_dist - wing_dist)

    return {
        "short_call": short_call,
        "short_put": short_put,
        "hedge_call": hedge_call,
        "hedge_put": hedge_put,
    }
