from datetime import datetime

LONG = "LONG"
SHORT = "SHORT"

TARGET_HIT = "TARGET_HIT"
STOPPED_LOSS = "STOPPED_LOSS"
STOPPED_BREAKEVEN = "STOPPED_BREAKEVEN"
EOD_EXIT = "EOD_EXIT"

# PDF section 5: SL buffer is 0.05%-0.10% of price; 0.075% is the midpoint.
SL_BUFFER_PCT = 0.075
# PDF section 5-6: minimum 1:2 reward-to-risk, breakeven once 1:1 is reached.
TARGET_RRR = 2.0
BREAKEVEN_RRR = 1.0
# PDF section 6: force-exit all open positions by 3:15 PM. The softer
# "1:30-2:00 PM, trail aggressively if sideways" rule is discretionary
# in the PDF and isn't simulated here - only the hard 3:15 cutoff is.
EOD_CUTOFF_TIME = "15:15:00"


def simulate_trade(
    direction: str,
    opening_high: float,
    opening_low: float,
    candles: list[tuple],
    *,
    max_entry_time: str | None = None,
    max_entry_lag: int | None = None,
    min_stop_pct: float = 0.0,
    stop_mode: str = "breakout",
    breakeven_rrr: float | None = BREAKEVEN_RRR,
    trail: bool = False,
    stop_floor_pct: float = 0.0,
    entry_mode: str = "breakout",
    retest_window: int = 6,
    retest_fill_buffer_pct: float = 0.0,
    target_rrr: float | None = None,
):
    """Simulate one ORB trade for a single stock on a single day.

    `candles` are 5-min candles from 09:30 onward (i.e. after the
    opening 09:15-09:30 range), oldest first, as
    (timestamp, open, high, low, close, volume).

    Optional research knobs (defaults reproduce the original behaviour):
    `max_entry_time` ("HH:MM:SS") drops fills after that time,
    `max_entry_lag` drops fills more than N candles after the breakout
    candle, `min_stop_pct` skips trades whose stop is closer than that
    % of entry, `stop_mode="range"` puts the stop beyond the opening
    range instead of the breakout candle, `breakeven_rrr=None` disables
    the breakeven move, and `stop_floor_pct` widens a tighter stop out to that % of entry
    (so tiny breakout candles don't produce cost-dominated trades), and
    `trail` trails the stop under the last two
    candles once the breakeven trigger is reached. `entry_mode="retest"`
    waits (up to `retest_window` candles) for a pullback to the opening
    range edge and buys/sells there, stopping beyond the pullback's extreme.

    Returns a trade dict, or None if no breakout ever triggered an
    actual entry fill that day (per PDF section 4: entry only fires
    when price later ticks past the confirming breakout candle's own
    high/low - the breakout candle's close alone doesn't fill it).
    """
    breakout_index = _find_breakout(direction, opening_high, opening_low, candles)
    if breakout_index is None:
        return None

    breakout_candle = candles[breakout_index]
    entry_level, stop_loss = _entry_and_stop(direction, breakout_candle)
    retest_index = None
    if entry_mode == "retest":
        edge = opening_high if direction == LONG else opening_low
        for j in range(breakout_index + 1, min(len(candles), breakout_index + 1 + retest_window)):
            fill_edge = edge * (1 - retest_fill_buffer_pct / 100) if direction == LONG else edge * (1 + retest_fill_buffer_pct / 100)
            touched = candles[j][3] <= fill_edge if direction == LONG else candles[j][2] >= fill_edge
            if touched:
                retest_index = j
                break
        if retest_index is None:
            return None
        structure = candles[breakout_index : retest_index + 1]
        entry_level = edge
        if direction == LONG:
            stop_loss = min(c[3] for c in structure) * (1 - SL_BUFFER_PCT / 100)
        else:
            stop_loss = max(c[2] for c in structure) * (1 + SL_BUFFER_PCT / 100)
        if (direction == LONG and stop_loss >= entry_level) or (direction == SHORT and stop_loss <= entry_level):
            return None
    elif stop_mode == "range":
        edge = opening_low if direction == LONG else opening_high
        stop_loss = edge * (1 - SL_BUFFER_PCT / 100) if direction == LONG else edge * (1 + SL_BUFFER_PCT / 100)
        if (direction == LONG and stop_loss >= entry_level) or (direction == SHORT and stop_loss <= entry_level):
            return None
    risk = abs(entry_level - stop_loss)
    if risk <= 0:
        return None
    if stop_floor_pct and 100 * risk / entry_level < stop_floor_pct:
        risk = entry_level * stop_floor_pct / 100
        stop_loss = _offset(direction, entry_level, -risk)
    if 100 * risk / entry_level < min_stop_pct:
        return None

    entry_index = (
        retest_index
        if retest_index is not None
        else _find_entry_fill(direction, entry_level, candles, breakout_index)
    )
    if entry_index is None:
        return None
    if max_entry_lag is not None and entry_index - breakout_index > max_entry_lag:
        return None
    if max_entry_time is not None and candles[entry_index][0][11:19] > max_entry_time:
        return None

    target = _offset(direction, entry_level, (TARGET_RRR if target_rrr is None else target_rrr) * risk)
    breakeven_trigger = (
        _offset(direction, entry_level, breakeven_rrr * risk) if breakeven_rrr is not None else None
    )
    entry_time = candles[entry_index][0]

    outcome, exit_time, exit_price = _walk_to_exit(
        direction, entry_index, candles, entry_level, stop_loss, target, breakeven_trigger, trail
    )

    return {
        "direction": direction,
        "opening_high": opening_high,
        "opening_low": opening_low,
        "breakout_time": breakout_candle[0],
        "entry_time": entry_time,
        "entry_price": entry_level,
        "stop_loss": stop_loss,
        "target": target,
        "risk_pct": round(100 * risk / entry_level, 3),
        "r_multiple": round(
            ((exit_price - entry_level) if direction == LONG else (entry_level - exit_price)) / risk, 3
        ),
        "outcome": outcome,
        "exit_time": exit_time,
        "exit_price": exit_price,
        "hold_minutes": _minutes_between(entry_time, exit_time),
        "achieved_1_2_by_close": outcome == TARGET_HIT,
    }


def _find_breakout(direction, opening_high, opening_low, candles):
    for i, candle in enumerate(candles):
        close = candle[4]
        if direction == LONG and close > opening_high:
            return i
        if direction == SHORT and close < opening_low:
            return i
    return None


def _entry_and_stop(direction, breakout_candle):
    _, _open, high, low, _close, _vol = breakout_candle
    if direction == LONG:
        return high, low * (1 - SL_BUFFER_PCT / 100)
    return low, high * (1 + SL_BUFFER_PCT / 100)


def _find_entry_fill(direction, entry_level, candles, breakout_index):
    for i in range(breakout_index + 1, len(candles)):
        high, low = candles[i][2], candles[i][3]
        if direction == LONG and high >= entry_level:
            return i
        if direction == SHORT and low <= entry_level:
            return i
    return None


def _offset(direction, price, amount):
    return price + amount if direction == LONG else price - amount


def _walk_to_exit(
    direction, entry_index, candles, entry_level, stop_loss, target, breakeven_trigger, trail=False
):
    current_stop = stop_loss
    at_breakeven = False
    last_candle_in_session = candles[entry_index]

    for i in range(entry_index, len(candles)):
        timestamp, _open, high, low, _close, _vol = candles[i]
        if timestamp[11:19] > EOD_CUTOFF_TIME:
            break
        last_candle_in_session = candles[i]

        if breakeven_trigger is not None:
            if not at_breakeven:
                reached = high >= breakeven_trigger if direction == LONG else low <= breakeven_trigger
                if reached:
                    current_stop = entry_level
                    at_breakeven = True
            elif trail and i >= entry_index + 2:
                prev = candles[i - 2 : i]
                if direction == LONG:
                    current_stop = max(current_stop, min(c[3] for c in prev))
                else:
                    current_stop = min(current_stop, max(c[2] for c in prev))

        stopped = low <= current_stop if direction == LONG else high >= current_stop
        hit_target = high >= target if direction == LONG else low <= target

        if stopped:
            return (STOPPED_BREAKEVEN if at_breakeven else STOPPED_LOSS), timestamp, current_stop
        if hit_target:
            return TARGET_HIT, timestamp, target

    return EOD_EXIT, last_candle_in_session[0], last_candle_in_session[4]


def _minutes_between(start_ts: str, end_ts: str) -> int:
    fmt = "%Y-%m-%dT%H:%M:%S%z"
    start = datetime.strptime(start_ts, fmt)
    end = datetime.strptime(end_ts, fmt)
    return round((end - start).total_seconds() / 60)
