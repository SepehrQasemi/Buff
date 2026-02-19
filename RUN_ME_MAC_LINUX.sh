#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
READY_URL="http://localhost:8000/api/v1/health/ready"
UI_URL="http://localhost:3000"
TIMEOUT_SECONDS="${BUFF_START_TIMEOUT_SECONDS:-180}"

ok() {
  echo "[OK] $1"
}

info() {
  echo "[INFO] $1"
}

fail() {
  echo "[FAIL] $1"
}

has_cmd() {
  command -v "$1" >/dev/null 2>&1
}

docker_running() {
  docker info >/dev/null 2>&1
}

compose_available() {
  docker compose version >/dev/null 2>&1
}

port_owners() {
  local port="$1"
  if has_cmd lsof; then
    lsof -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | awk -v p="$port" 'NR>1 {print "Port " p ": PID " $2 " (" $1 ")"}'
    return
  fi
  if has_cmd ss; then
    ss -ltnp "( sport = :$port )" 2>/dev/null | awk -v p="$port" 'NR>1 {print "Port " p ": " $0}'
    return
  fi
  if has_cmd netstat; then
    netstat -lntp 2>/dev/null | awk -v p=":$port" '$4 ~ p {print "Port " substr(p,2) ": " $0}'
  fi
}

collect_port_conflicts() {
  local out=""
  local line=""
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    out+="$line"$'\n'
  done < <(port_owners 3000)
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    out+="$line"$'\n'
  done < <(port_owners 8000)
  printf '%s' "$out"
}

readiness_ready() {
  local payload="$1"
  printf '%s' "$payload" | grep -Eq '"status"[[:space:]]*:[[:space:]]*"ready"'
}

open_ui() {
  if has_cmd open; then
    open "$UI_URL" >/dev/null 2>&1 || true
    return
  fi
  if has_cmd xdg-open; then
    xdg-open "$UI_URL" >/dev/null 2>&1 || true
  fi
}

show_failure_diagnostics() {
  if ! docker_running; then
    fail "Docker is not running. Start Docker Desktop (or Docker Engine), then run again."
  fi
  if ! compose_available; then
    fail "docker compose is not available. Install Docker Compose v2."
  fi
  local conflicts
  conflicts=$(collect_port_conflicts)
  if [[ -n "$conflicts" ]]; then
    fail "Required ports are in use."
    printf '%s' "$conflicts"
  fi
}

info "Starting Buff local platform..."

if ! has_cmd docker; then
  fail "Docker is not installed. Install Docker Desktop, then run this script again."
  exit 1
fi

if ! docker_running; then
  fail "Docker is not running. Start Docker Desktop (or Docker Engine), then run again."
  exit 1
fi

if ! compose_available; then
  fail "docker compose is not available. Install Docker Compose v2."
  exit 1
fi

initial_conflicts=$(collect_port_conflicts)
if [[ -n "$initial_conflicts" ]]; then
  fail "Required ports are in use."
  printf '%s' "$initial_conflicts"
  exit 1
fi

if [[ ! -f "$REPO_ROOT/scripts/dev_up.sh" ]]; then
  fail "Missing script: scripts/dev_up.sh"
  exit 1
fi

info "Launching containers with docker compose..."
if ! bash "$REPO_ROOT/scripts/dev_up.sh" up; then
  fail "docker compose up failed."
  show_failure_diagnostics
  exit 1
fi

info "Waiting for readiness at $READY_URL (timeout: ${TIMEOUT_SECONDS}s)..."
deadline=$((SECONDS + TIMEOUT_SECONDS))
last_ready_body=""

while (( SECONDS < deadline )); do
  current_body=$(curl -sS --max-time 5 "$READY_URL" 2>/dev/null || true)
  if [[ -n "$current_body" ]]; then
    last_ready_body="$current_body"
    if readiness_ready "$current_body"; then
      ok "Buff is ready."
      ok "UI URL: $UI_URL"
      open_ui
      exit 0
    fi
  fi
  sleep 2
done

fail "Readiness did not become ready before timeout."
show_failure_diagnostics
final_body=$(curl -sS --max-time 5 "$READY_URL" 2>/dev/null || true)
if [[ -n "$final_body" ]]; then
  last_ready_body="$final_body"
fi
if [[ -n "$last_ready_body" ]]; then
  echo "[INFO] Last /health/ready response: $last_ready_body"
else
  echo "[INFO] Last /health/ready response: <no response>"
fi
exit 1
