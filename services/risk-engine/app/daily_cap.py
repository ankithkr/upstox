"""Enforces the v2 strategy's `max_trades_per_day` cap and one-position-
per-symbol-per-day rule (README section 7 / params.py's
`max_trades_per_day`). Signals arrive in chronological order already
(they're emitted live, in the order breakouts actually happen), so
accepting in arrival order up to the cap reproduces snapshots.py's
"first entries win" ordering without needing to re-sort anything.
"""

from __future__ import annotations


class DailyCapTracker:
    def __init__(self, max_trades_per_day: int):
        self.max_trades_per_day = max_trades_per_day
        self._date: str | None = None
        self._accepted_symbols: set[str] = set()

    def reset_if_new_day(self, date: str) -> bool:
        """Returns True if this call started a new day (caller should
        refresh its equity/cash baseline)."""
        if date == self._date:
            return False
        self._date = date
        self._accepted_symbols = set()
        return True

    def can_accept(self, symbol: str) -> tuple[bool, str | None]:
        if symbol in self._accepted_symbols:
            return False, "already has a position today"
        if len(self._accepted_symbols) >= self.max_trades_per_day:
            return False, f"already {self.max_trades_per_day} trades today"
        return True, None

    def record_accepted(self, symbol: str) -> None:
        self._accepted_symbols.add(symbol)
