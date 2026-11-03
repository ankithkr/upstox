"""Broker abstraction. PaperBroker implements this now; a live Upstox broker
implements the same interface later without strategy/risk engines changing."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .models import OrderIntent, Position, Trade


class Broker(ABC):
    @abstractmethod
    async def place_order(self, order: OrderIntent) -> Trade:
        ...

    @abstractmethod
    async def get_trade(self, order_id: str) -> Trade | None:
        ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> None:
        ...

    @abstractmethod
    async def get_positions(self) -> list[Position]:
        ...
