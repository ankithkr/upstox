"""Tracks realised equity across closed trades for the running process.
Phase 5 scope: equity moves only on a trade's close (gross_pnl - charges);
there is no mark-to-market of open positions yet.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Ledger:
    starting_capital: float
    realized_net_pnl: float = 0.0

    @property
    def equity(self) -> float:
        return self.starting_capital + self.realized_net_pnl

    def apply_closed_trade(self, net_pnl: float) -> None:
        self.realized_net_pnl += net_pnl
