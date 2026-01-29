from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class OrderResult:
    order_id: str
    filled_qty: float
    status: str


class Broker(Protocol):
    def submit_order(self, symbol: str, side: str, quantity: float) -> OrderResult:
        ...

    def cancel_order(self, order_id: str) -> None:
        ...


class PaperBroker:
    def __init__(self) -> None:
        self.submitted: list[OrderResult] = []
        self._next_id = 1

    def submit_order(self, symbol: str, side: str, quantity: float) -> OrderResult:
        order_id = f"paper-{self._next_id}"
        self._next_id += 1
        result = OrderResult(order_id=order_id, filled_qty=quantity, status="filled")
        self.submitted.append(result)
        return result

    def cancel_order(self, order_id: str) -> None:
        return None


class LiveBroker:
    def submit_order(self, symbol: str, side: str, quantity: float) -> OrderResult:
        raise NotImplementedError("LiveBroker is a stub only.")

    def cancel_order(self, order_id: str) -> None:
        raise NotImplementedError("LiveBroker is a stub only.")
