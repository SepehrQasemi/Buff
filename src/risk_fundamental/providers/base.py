"""Snapshot provider interfaces for fundamental risk."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from ..contracts import FundamentalSnapshot


class SnapshotProvider(ABC):
    @abstractmethod
    def get_snapshot(self, at: datetime) -> FundamentalSnapshot:
        raise NotImplementedError

    @abstractmethod
    def list_snapshots(self) -> list[FundamentalSnapshot]:
        raise NotImplementedError
