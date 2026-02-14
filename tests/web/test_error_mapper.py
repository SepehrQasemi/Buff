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
import { ERROR_HINTS, formatApiError, mapApiError } from './apps/web/lib/errors.js';

const requiredCodes = [
  'RUNS_ROOT_UNSET',
  'RUNS_ROOT_MISSING',
  'RUNS_ROOT_INVALID',
  'RUNS_ROOT_NOT_WRITABLE',
  'DATA_SOURCE_NOT_FOUND',
  'DATA_INVALID',
  'trades_missing',
  'trades_invalid',
  'ohlcv_missing',
  'ohlcv_invalid',
  'metrics_missing',
  'metrics_invalid',
  'timeline_missing',
  'timeline_invalid',
];

for (const code of requiredCodes) {
  if (!ERROR_HINTS[code]) {
    throw new Error(`Missing error hint for ${code}`);
  }
  if (!ERROR_HINTS[code].title || !ERROR_HINTS[code].fix) {
    throw new Error(`Incomplete error hint for ${code}`);
  }
}

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
if (!formatted.includes('Fix:')) {
  throw new Error(`formatApiError missing fix guidance: ${formatted}`);
}
"""
    subprocess.run(
        [node, "--input-type=module", "-e", script],
        cwd=repo_root,
        check=True,
    )
