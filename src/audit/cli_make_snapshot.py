from __future__ import annotations

import argparse
import json
from pathlib import Path

from audit.snapshot import create_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a deterministic replay snapshot.")
    parser.add_argument("--input", required=True, help="Path to snapshot payload JSON")
    parser.add_argument(
        "--out",
        required=True,
        help="Output directory for snapshot artifacts",
    )
    args = parser.parse_args()

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    out_path = create_snapshot(payload, args.out)
    print(out_path.as_posix())


if __name__ == "__main__":
    main()
