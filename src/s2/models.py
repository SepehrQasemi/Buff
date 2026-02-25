from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
from typing import Mapping


def _parse_utc(ts_utc: str) -> datetime:
    text = str(ts_utc).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class S2ModelError(RuntimeError):
    pass


class FundingDataMissingError(S2ModelError):
    def __init__(self, ts_utc: str):
        super().__init__(f"missing_critical_funding_window:{ts_utc}")
        self.ts_utc = ts_utc


class PositionInvariantError(S2ModelError):
    def __init__(self, message: str):
        super().__init__(message)


@dataclass(frozen=True)
class FeeModel:
    maker_bps: float = 2.0
    taker_bps: float = 4.0
    version: str = "fee.v1"

    def fee_for_notional(self, notional_quote: float, *, liquidity: str = "taker") -> float:
        notional = abs(float(notional_quote))
        rate_bps = self.maker_bps if liquidity.lower() == "maker" else self.taker_bps
        if rate_bps < 0:
            raise S2ModelError("fee_model_negative_bps")
        return notional * (float(rate_bps) / 10_000.0)


@dataclass(frozen=True)
class SlippageBucket:
    max_notional_quote: float | None
    bps: float


@dataclass(frozen=True)
class SlippageModel:
    buckets: tuple[SlippageBucket, ...]
    stress_multiplier: float = 1.0
    version: str = "slippage.v1"

    def bps_for_notional(self, notional_quote: float) -> float:
        notional = abs(float(notional_quote))
        for bucket in self.buckets:
            if bucket.max_notional_quote is None or notional <= float(bucket.max_notional_quote):
                return float(bucket.bps) * float(self.stress_multiplier)
        return 0.0

    def apply(self, reference_price: float, *, side: str, notional_quote: float) -> float:
        price = float(reference_price)
        if price <= 0:
            raise S2ModelError("slippage_invalid_reference_price")
        bps = self.bps_for_notional(notional_quote)
        factor = 1.0 + (bps / 10_000.0) if side.upper() == "BUY" else 1.0 - (bps / 10_000.0)
        return price * factor


@dataclass(frozen=True)
class FundingModel:
    interval_minutes: int = 480
    rates_by_ts_utc: Mapping[str, float] = field(default_factory=dict)
    version: str = "funding.v1"

    def is_due(self, ts_utc: str) -> bool:
        interval = int(self.interval_minutes)
        if interval <= 0:
            return False
        ts = _parse_utc(ts_utc)
        total_minutes = int(ts.timestamp() // 60)
        return total_minutes % interval == 0

    def funding_rate(self, ts_utc: str, *, has_open_position: bool) -> float | None:
        if not self.is_due(ts_utc):
            return None
        raw = self.rates_by_ts_utc.get(ts_utc)
        if raw is None:
            if has_open_position:
                raise FundingDataMissingError(ts_utc)
            return None
        return float(raw)


def funding_transfer_quote(position_qty: float, mark_price: float, funding_rate: float) -> float:
    qty = float(position_qty)
    if qty == 0.0:
        return 0.0
    notional = abs(qty * float(mark_price))
    if qty > 0:
        return -notional * float(funding_rate)
    return notional * float(funding_rate)


@dataclass
class PositionAccounting:
    qty: float = 0.0
    avg_entry_price: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    cumulative_fees: float = 0.0
    cumulative_slippage: float = 0.0
    cumulative_funding: float = 0.0
    liquidation_count: int = 0

    def _check_finite(self) -> None:
        values = (
            self.qty,
            self.avg_entry_price,
            self.realized_pnl,
            self.unrealized_pnl,
            self.cumulative_fees,
            self.cumulative_slippage,
            self.cumulative_funding,
        )
        if not all(math.isfinite(float(value)) for value in values):
            raise PositionInvariantError("position_non_finite")

    def assert_invariants(self) -> None:
        self._check_finite()
        if self.qty == 0.0:
            if abs(self.avg_entry_price) > 1e-12:
                raise PositionInvariantError("flat_position_nonzero_entry")
            if abs(self.unrealized_pnl) > 1e-12:
                raise PositionInvariantError("flat_position_nonzero_unrealized")
        else:
            if self.avg_entry_price <= 0:
                raise PositionInvariantError("open_position_nonpositive_entry")

    def apply_fill(self, qty_delta: float, fill_price: float) -> float:
        qty_delta = float(qty_delta)
        fill_price = float(fill_price)
        if qty_delta == 0.0:
            return 0.0
        if fill_price <= 0:
            raise S2ModelError("fill_price_nonpositive")

        prior_qty = self.qty
        prior_entry = self.avg_entry_price
        realized_delta = 0.0

        if (
            prior_qty == 0.0
            or (prior_qty > 0 and qty_delta > 0)
            or (prior_qty < 0 and qty_delta < 0)
        ):
            new_qty = prior_qty + qty_delta
            if new_qty == 0.0:
                self.qty = 0.0
                self.avg_entry_price = 0.0
            elif prior_qty == 0.0:
                self.qty = new_qty
                self.avg_entry_price = fill_price
            else:
                weighted_notional = (abs(prior_qty) * prior_entry) + (abs(qty_delta) * fill_price)
                self.qty = new_qty
                self.avg_entry_price = weighted_notional / abs(new_qty)
            self.unrealized_pnl = 0.0
            self.assert_invariants()
            return 0.0

        close_qty = min(abs(prior_qty), abs(qty_delta))
        if prior_qty > 0:
            realized_delta = close_qty * (fill_price - prior_entry)
        else:
            realized_delta = close_qty * (prior_entry - fill_price)
        self.realized_pnl += realized_delta

        new_qty = prior_qty + qty_delta
        if new_qty == 0.0:
            self.qty = 0.0
            self.avg_entry_price = 0.0
        elif (prior_qty > 0 and new_qty > 0) or (prior_qty < 0 and new_qty < 0):
            self.qty = new_qty
        else:
            self.qty = new_qty
            self.avg_entry_price = fill_price

        self.unrealized_pnl = 0.0
        self.assert_invariants()
        return realized_delta

    def mark_to_market(self, mark_price: float) -> float:
        mark = float(mark_price)
        if mark <= 0:
            raise S2ModelError("mark_price_nonpositive")
        if self.qty == 0.0:
            self.unrealized_pnl = 0.0
        elif self.qty > 0:
            self.unrealized_pnl = (mark - self.avg_entry_price) * self.qty
        else:
            self.unrealized_pnl = (self.avg_entry_price - mark) * abs(self.qty)
        self.assert_invariants()
        return self.unrealized_pnl


@dataclass(frozen=True)
class LiquidationModel:
    maintenance_margin_ratio: float = 0.005
    conservative_buffer_ratio: float = 0.1
    version: str = "liquidation.v1"

    def threshold(self, notional_quote: float) -> float:
        notional = abs(float(notional_quote))
        maintenance = notional * float(self.maintenance_margin_ratio)
        return maintenance * (1.0 + float(self.conservative_buffer_ratio))

    def should_liquidate(self, *, equity_quote: float, notional_quote: float) -> bool:
        notional = abs(float(notional_quote))
        if notional <= 0.0:
            return False
        return float(equity_quote) <= self.threshold(notional)
