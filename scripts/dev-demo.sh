#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
DEMO_RUN_ID=${DEMO_RUN_ID:-stage5_demo}
ARTIFACTS_ROOT=${ARTIFACTS_ROOT:-"$REPO_ROOT/tests/fixtures/artifacts"}
API_PORT=${API_PORT:-8000}
UI_PORT=${UI_PORT:-3000}

if [[ -z "${PYTHON_BIN:-}" ]]; then
  if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
    PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
  elif [[ -x "$REPO_ROOT/.venv/Scripts/python.exe" ]]; then
    PYTHON_BIN="$REPO_ROOT/.venv/Scripts/python.exe"
  else
    PYTHON_BIN="python"
  fi
fi

export ARTIFACTS_ROOT
export NEXT_PUBLIC_API_BASE="http://127.0.0.1:${API_PORT}/api/v1"
unset RUNS_ROOT

(
  cd "$REPO_ROOT"
  "$PYTHON_BIN" -m uvicorn apps.api.main:app --host 127.0.0.1 --port "$API_PORT" --reload
) &
API_PID=$!

(
  cd "$REPO_ROOT/apps/web"
  npm run dev -- --port "$UI_PORT"
) &
UI_PID=$!

echo "Stage-5 demo running (read-only)"
echo "Open http://localhost:${UI_PORT}/runs/${DEMO_RUN_ID}"

cleanup() {
  kill "$UI_PID" "$API_PID" 2>/dev/null || true
}
trap cleanup EXIT

wait
