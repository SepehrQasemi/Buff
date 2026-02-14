import json
import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
NODE = shutil.which("node")


def run_node(script: str) -> dict:
    if not NODE:
        pytest.skip("node not available for web error mapping tests")
    proc = subprocess.run(
        [NODE, "--input-type=module", "-e", script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_runs_root_unset_mapping():
    script = """
import { mapErrorPayload } from "./apps/web/lib/errorMapping.js";
const mapped = mapErrorPayload({
  code: "RUNS_ROOT_UNSET",
  message: "RUNS_ROOT is not set",
  details: { env: "RUNS_ROOT" },
  status: 503,
});
console.log(JSON.stringify(mapped));
"""
    mapped = run_node(script)
    assert mapped["title"] == "RUNS_ROOT is not set"
    assert "RUNS_ROOT" in mapped["summary"]
    assert mapped["actions"]
    assert mapped["help"]["href"].endswith("FIRST_RUN.md#troubleshooting")


def test_data_invalid_missing_column_mapping():
    script = """
import { mapErrorPayload } from "./apps/web/lib/errorMapping.js";
const mapped = mapErrorPayload({
  code: "DATA_INVALID",
  message: "Missing required column: close",
  status: 400,
});
console.log(JSON.stringify(mapped));
"""
    mapped = run_node(script)
    assert mapped["title"] == "CSV data invalid"
    assert "close" in mapped["summary"]
    assert mapped["help"]["href"].endswith("FIRST_RUN.md#csv-requirements")


def test_run_corrupted_mapping():
    script = """
import { mapErrorPayload } from "./apps/web/lib/errorMapping.js";
const mapped = mapErrorPayload({
  code: "RUN_CORRUPTED",
  message: "Run artifacts missing",
  status: 409,
});
console.log(JSON.stringify(mapped));
"""
    mapped = run_node(script)
    assert mapped["title"] == "Run artifacts missing"
    assert mapped["actions"]
