from __future__ import annotations

from pathlib import Path

import pandas as pd


def load_parquet(path: Path, columns: list[str] | None = None) -> pd.DataFrame:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"missing_artifact:{path}")
    return pd.read_parquet(path, columns=columns)
