#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
RUNS_ROOT_HOST=${RUNS_ROOT_HOST:-"$REPO_ROOT/.runs_compose"}
ACTION=${1:-up}
shift || true

compose() {
  (
    cd "$REPO_ROOT"
    docker compose "$@"
  )
}

ensure_safe_runs_root() {
  mkdir -p "$RUNS_ROOT_HOST"
  local resolved_repo
  local resolved_runs
  resolved_repo=$(cd "$REPO_ROOT" && pwd -P)
  resolved_runs=$(cd "$RUNS_ROOT_HOST" && pwd -P)
  if [[ "$resolved_runs" != "$resolved_repo"* ]]; then
    echo "reset-runs refused: RUNS_ROOT_HOST must be under repo root ($resolved_repo)" >&2
    exit 1
  fi
  if [[ "$resolved_runs" == "/" || "$resolved_runs" == "$resolved_repo" ]]; then
    echo "reset-runs refused: unsafe RUNS_ROOT_HOST ($resolved_runs)" >&2
    exit 1
  fi
}

case "$ACTION" in
  up)
    mkdir -p "$RUNS_ROOT_HOST"
    compose up -d --build "$@"
    ;;
  down)
    compose down --remove-orphans "$@"
    ;;
  logs)
    compose logs -f "$@"
    ;;
  reset-runs)
    ensure_safe_runs_root
    find "$RUNS_ROOT_HOST" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
    ;;
  *)
    echo "Usage: scripts/dev_up.sh [up|down|logs|reset-runs] [service...]" >&2
    exit 1
    ;;
esac
