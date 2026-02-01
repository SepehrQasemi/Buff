from __future__ import annotations

import argparse
import json
from pathlib import Path

from audit.decision_record import DecisionRecord


def main() -> None:
    parser = argparse.ArgumentParser(description="Write a canonical decision record JSON.")
    parser.add_argument("--input", required=True, help="Path to decision record JSON payload")
    parser.add_argument("--out", required=True, help="Output JSON path")
    args = parser.parse_args()

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    record = DecisionRecord.from_dict(payload)

    out_path = Path(args.out)
    if out_path.suffix.lower() != ".json":
        date_part = record.ts_utc[:10]
        out_path = out_path / date_part / f"decision_{record.decision_id}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(record.to_canonical_json(), encoding="utf-8")

    print(out_path.as_posix())


if __name__ == "__main__":
    main()
