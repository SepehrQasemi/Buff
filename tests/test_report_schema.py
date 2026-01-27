"""Schema validation tests for data_quality.json."""

import json
from pathlib import Path

import pandas as pd
import pytest

from buff.data.report import build_report
from buff.data.store import ohlcv_parquet_path, save_parquet


pytestmark = pytest.mark.unit


def _minimal_validate(schema: dict, payload: dict) -> None:
    required = schema.get("required", [])
    for key in required:
        if key not in payload:
            raise AssertionError(f"Missing required key: {key}")

    report_required = schema["definitions"]["report"]["required"]
    for key in report_required:
        if key not in payload["global"]:
            raise AssertionError(f"Missing required key in global: {key}")

    per_symbol = payload.get("per_symbol", [])
    assert isinstance(per_symbol, list)
    for item in per_symbol:
        for key in report_required:
            if key not in item:
                raise AssertionError(f"Missing required key in per_symbol: {key}")


def test_report_schema_validation(tmp_path: Path) -> None:
    fixtures_dir = Path("tests/fixtures/ohlcv")
    data_dir = tmp_path / "data" / "ohlcv"

    symbols = ["BTC/USDT", "ETH/USDT"]
    timeframe = "1m"

    for symbol in symbols:
        csv_name = symbol.replace("/", "_") + "_1m.csv"
        df = pd.read_csv(fixtures_dir / csv_name)
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
        save_parquet(df, str(ohlcv_parquet_path(data_dir, symbol, timeframe)))

    report = build_report(data_dir, symbols, [timeframe], strict=True)
    schema = json.loads(Path("schemas/data_quality.schema.json").read_text(encoding="utf-8"))

    try:
        import jsonschema
        jsonschema.validate(instance=report, schema=schema)
    except ModuleNotFoundError:
        _minimal_validate(schema, report)
