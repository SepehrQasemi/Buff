from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


def test_error_mapper_node_smoke() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not available")

    repo_root = Path(__file__).resolve().parents[2]
    script = """
import { formatApiError, mapApiError } from './apps/web/lib/errors.js';

const result = {
  status: 404,
  data: {
    detail: {
      code: 'ohlcv_missing',
      message: 'OHLCV artifact missing',
      details: { run_id: 'stage5_demo' },
    },
  },
};

const mapped = mapApiError(result);
if (!mapped || !mapped.includes('OHLCV')) {
  throw new Error(`mapApiError missing mapping: ${mapped}`);
}
const formatted = formatApiError(result, 'fallback');
if (!formatted.includes('HTTP 404')) {
  throw new Error(`formatApiError missing HTTP code: ${formatted}`);
}
if (!formatted.includes('ARTIFACTS_ROOT')) {
  throw new Error(`formatApiError missing guidance: ${formatted}`);
}
"""
    subprocess.run(
        [node, "--input-type=module", "-e", script],
        cwd=repo_root,
        check=True,
    )
