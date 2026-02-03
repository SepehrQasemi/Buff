"""Metadata helpers for deterministic feature runs."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from buff.features.canonical import canonical_json_bytes


def sha256_file(path: str | Path) -> str:
    """Compute sha256 for a file in 1MB chunks."""
    file_path = Path(path)
    hasher = hashlib.sha256()
    with file_path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def get_git_sha() -> str | None:
    """Return current git SHA, or None if unavailable."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    sha = result.stdout.strip()
    return sha or None


def write_json(path: str | Path, obj: dict[str, Any]) -> None:
    """Write JSON with stable formatting."""
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(obj, handle, indent=2, sort_keys=True)
        handle.write("\n")


def build_source_fingerprint(
    *,
    file_hashes: dict[str, str],
    schema: dict[str, object],
) -> str:
    payload = {"files": dict(sorted(file_hashes.items())), "schema": schema}
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def build_metadata(
    *,
    input_path: str,
    input_format: str,
    input_sha256: str,
    output_path: str,
    output_sha256: str,
    row_count: int,
    columns: list[str],
    features: list[str],
    feature_params: dict[str, int],
) -> dict[str, Any]:
    """Build metadata for a feature run."""
    return {
        "schema_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": get_git_sha(),
        "input_path": input_path,
        "input_format": input_format,
        "input_sha256": input_sha256,
        "output_path": output_path,
        "output_format": "parquet",
        "output_sha256": output_sha256,
        "row_count": row_count,
        "columns": columns,
        "features": features,
        "feature_params": feature_params,
    }
