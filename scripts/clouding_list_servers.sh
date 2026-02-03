#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${CLOUDING_APIKEY:-}" ]]; then
  echo "CLOUDING_APIKEY is not set. Export it before running this script." >&2
  exit 1
fi

response=$(curl -sS -w "\n%{http_code}" \
  -H "Accept: application/json" \
  -H "X-API-KEY: ${CLOUDING_APIKEY}" \
  "https://api.clouding.io/v1/servers")

http_code=$(echo "${response}" | tail -n 1)
body=$(echo "${response}" | sed '$d')

if [[ "${http_code}" -lt 200 || "${http_code}" -ge 300 ]]; then
  echo "Clouding API request failed with HTTP ${http_code}." >&2
  echo "${body}" | head -c 500 >&2
  echo "" >&2
  exit 1
fi

CLOUDING_RESPONSE="${body}" python - <<'PY'
import json, os, sys

raw = os.environ.get("CLOUDING_RESPONSE", "")
try:
    data = json.loads(raw)
except Exception:
    print("Failed to parse Clouding API response as JSON.", file=sys.stderr)
    sys.exit(1)

if isinstance(data, list):
    servers = data
elif isinstance(data, dict) and "servers" in data:
    servers = data.get("servers", [])
elif isinstance(data, dict) and isinstance(data.get("data"), list):
    servers = data.get("data", [])
else:
    servers = []

print(f"{'NAME':30} {'ID':18} {'STATUS'}")
if not servers:
    print("No servers found.")
    sys.exit(0)

for s in servers:
    name = str(s.get("name", "") or "")
    sid = str(s.get("id", "") or "")
    status = str(s.get("status", "") or "")
    print(f"{name[:30]:30} {sid[:18]:18} {status}")
PY
