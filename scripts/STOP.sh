#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

ok() {
  echo "[OK] $1"
}

fail() {
  echo "[FAIL] $1"
}

if ! command -v docker >/dev/null 2>&1; then
  fail "Docker is not installed."
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  fail "docker compose is not available."
  exit 1
fi

if [[ ! -f "$REPO_ROOT/scripts/dev_up.sh" ]]; then
  fail "Missing script: scripts/dev_up.sh"
  exit 1
fi

echo "[INFO] Stopping Buff containers..."
if ! bash "$REPO_ROOT/scripts/dev_up.sh" down; then
  fail "Failed to stop Buff containers."
  exit 1
fi

ok "Buff services stopped."
ok "Existing run data was not deleted."
