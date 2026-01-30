from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator


@dataclass
class MarketStateFeed:
    path: str
    items: list[dict] = field(default_factory=list)
    errors: int = 0

    def __iter__(self) -> Iterator[dict]:
        return iter(self.items)


def load_market_state_feed(path: str) -> MarketStateFeed:
    feed = MarketStateFeed(path=path)
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            feed.errors += 1
            continue
        if not isinstance(obj, dict):
            feed.errors += 1
            continue
        feed.items.append(obj)
    return feed


def cycling_feed(iterable: Iterator[dict]) -> Iterator[dict]:
    items = list(iterable)
    if not items:
        while True:
            yield {}
    while True:
        for item in items:
            yield item
