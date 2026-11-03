"""Shared data contracts passed between engines over Redis and Supabase."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class Candle(BaseModel):
    symbol: str
    timeframe: str  # e.g. "5m", "15m", "1d"
    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class Signal(BaseModel):
    id: str
    symbol: str
    direction: Direction
    sector: str
    detected_at: datetime
    breakout_price: float
    stop_price: float
    target_price: float
    breakeven_trigger: float | None = None
    filters_passed: list[str]


class OrderIntent(BaseModel):
    id: str
    signal_id: str
    symbol: str
    direction: Direction
    qty: int
    entry_price: float
    stop_price: float
    target_price: float
    breakeven_trigger: float | None = None
    risk_amount: float


class TradeStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    SKIPPED = "SKIPPED"


class Trade(BaseModel):
    id: str
    order_id: str
    symbol: str
    direction: Direction
    status: TradeStatus
    qty: int
    entry_price: float | None = None
    entry_time: datetime | None = None
    exit_price: float | None = None
    exit_time: datetime | None = None
    gross_pnl: float | None = None
    charges: float | None = None
    net_pnl: float | None = None
    r_multiple: float | None = None


class Position(BaseModel):
    symbol: str
    direction: Direction
    qty: int
    avg_entry_price: float
