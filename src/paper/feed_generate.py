from __future__ import annotations

import argparse
import json
import random
from pathlib import Path


def _random_choice(rng: random.Random, options: list[tuple[str, int]]) -> str:
    total = sum(weight for _, weight in options)
    roll = rng.randint(1, total)
    cumulative = 0
    for value, weight in options:
        cumulative += weight
        if roll <= cumulative:
            return value
    return options[-1][0]


def generate_market_state(rng: random.Random) -> dict:
    trend_state = _random_choice(rng, [("UP", 30), ("DOWN", 30), ("RANGE", 40)])
    volatility_regime = _random_choice(rng, [("LOW", 25), ("HIGH", 25), ("EXPANDING", 50)])
    momentum_state = "SPIKE" if rng.random() < 0.05 else "NORMAL"
    market_state: dict[str, str] = {
        "trend_state": trend_state,
        "volatility_regime": volatility_regime,
        "momentum_state": momentum_state,
    }
    if rng.random() < 0.4:
        market_state["range_state"] = _random_choice(rng, [("TIGHT", 50), ("WIDE", 50)])
    return market_state


def write_feed(out_path: Path, rows: int, seed: int, flush_every: int = 1000) -> None:
    rng = random.Random(seed)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        for idx in range(rows):
            record = generate_market_state(rng)
            handle.write(json.dumps(record, separators=(",", ":"), ensure_ascii=False))
            handle.write("\n")
            if (idx + 1) % flush_every == 0:
                handle.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic market_state JSONL feed.")
    parser.add_argument("--out", required=True)
    parser.add_argument("--rows", type=int, default=500000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    write_feed(Path(args.out), args.rows, args.seed)


if __name__ == "__main__":
    main()
