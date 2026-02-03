from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class OrderResult:
    order_id: str
    filled_qty: float
    status: str


class BrokerError(RuntimeError):
    pass


class Broker(Protocol):
    def submit_order(self, symbol: str, side: str, quantity: float) -> OrderResult: ...

    def cancel_order(self, order_id: str) -> None: ...


class PaperBroker:
    def __init__(
        self,
        *,
        fail_on_submit: bool = False,
        fail_after: int | None = None,
        error: Exception | None = None,
    ) -> None:
        self.submitted: list[OrderResult] = []
        self._next_id = 1
        self._submit_attempts = 0
        self._fail_on_submit = fail_on_submit
        self._fail_after = fail_after
        self._error = error or BrokerError("broker_failure")

    def submit_order(self, symbol: str, side: str, quantity: float) -> OrderResult:
        self._submit_attempts += 1
        if self._fail_on_submit:
            raise self._error
        if self._fail_after is not None and self._submit_attempts > self._fail_after:
            raise self._error
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
