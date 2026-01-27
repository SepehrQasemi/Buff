"""Schema validation tests for data_quality.json."""

import json
from pathlib import Path

import pandas as pd
import pytest

from buff.data.report import build_report
from buff.data.store import save_parquet, symbol_to_filename


pytestmark = pytest.mark.unit


def _minimal_validate(schema: dict, payload: dict) -> None:
    required = schema.get("required", [])
    for key in required:
        if key not in payload:
            raise AssertionError(f"Missing required key: {key}")

    for section in ["global"]:
        for key in schema["definitions"]["report"]["required"]:
            if key not in payload[section]:
                raise AssertionError(f"Missing required key in {section}: {key}")

    per_symbol = payload.get("per_symbol", [])
    assert isinstance(per_symbol, list)
    for item in per_symbol:
        for key in schema["definitions"]["report"]["required"]:
            if key not in item:
                raise AssertionError(f"Missing required key in per_symbol: {key}")


def test_report_schema_validation(tmp_path: Path) -> None:
    fixtures_dir = Path("tests/fixtures/ohlcv")
    data_dir = tmp_path / "data" / "clean"
    data_dir.mkdir(parents=True, exist_ok=True)

    symbols = ["BTC/USDT", "ETH/USDT"]
    timeframe = "1h"

    for symbol in symbols:
        csv_name = symbol_to_filename(symbol, timeframe).replace(".parquet", ".csv")
        df = pd.read_csv(fixtures_dir / csv_name)
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
        save_parquet(df, str(data_dir / symbol_to_filename(symbol, timeframe)))

    report = build_report(data_dir, symbols, timeframe, strict=True)
    schema = json.loads(Path("schemas/data_quality.schema.json").read_text(encoding="utf-8"))

    try:
        import jsonschema
        jsonschema.validate(instance=report, schema=schema)
    except ModuleNotFoundError:
        _minimal_validate(schema, report)
