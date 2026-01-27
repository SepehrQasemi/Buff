"""Verify data quality report against actual data."""

import json
from pathlib import Path

import pandas as pd

from buff.data.store import load_parquet, symbol_to_filename


def verify_outputs() -> None:
    """Verify reports/data_quality.json against saved parquet files.
    
    Checks that:
    - zero_volume_examples: ts exist in data and have volume <= 0
    - missing_examples: ts do NOT exist in data (correctly identified as missing)
    """
    report_path = Path("reports/data_quality.json")
    data_dir = Path("data/clean")

    if not report_path.exists():
        print(f"✗ Report not found: {report_path}")
        return

    with open(report_path, "r") as f:
        report = json.load(f)

    verified_count = 0
    errors = []

    for symbol, metrics in report.items():
        if "error" in metrics:
            # Skip symbols with errors
            continue

        filename = metrics.get("file")
        if not filename:
            errors.append(f"✗ {symbol}: no file in report")
            continue

        filepath = data_dir / filename
        if not filepath.exists():
            errors.append(f"✗ {symbol}: parquet file not found at {filepath}")
            continue

        try:
            df = load_parquet(str(filepath))
        except Exception as e:
            errors.append(f"✗ {symbol}: failed to load parquet: {e}")
            continue

        # Verify zero_volume_examples
        zero_vol_examples = metrics.get("zero_volume_examples", [])
        for ts_str in zero_vol_examples:
            ts = pd.Timestamp(ts_str)
            matching = df[df["ts"] == ts]
            if matching.empty:
                errors.append(f"✗ {symbol}: zero_volume example ts not in data: {ts_str}")
            else:
                vol = matching["volume"].iloc[0]
                if vol > 0:
                    errors.append(
                        f"✗ {symbol}: example ts {ts_str} has volume {vol} (expected <= 0)"
                    )

        # Verify missing_examples
        missing_examples = metrics.get("missing_examples", [])
        for ts_str in missing_examples:
            ts = pd.Timestamp(ts_str)
            matching = df[df["ts"] == ts]
            if not matching.empty:
                errors.append(f"✗ {symbol}: missing_examples ts found in data: {ts_str}")

        verified_count += 1

    if errors:
        for err in errors:
            print(err)
        print(f"\n✗ Verification failed with {len(errors)} error(s)")
    else:
        print(f"✓ OK: verified {verified_count} symbol(s)")


if __name__ == "__main__":
    verify_outputs()
