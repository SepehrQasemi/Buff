#!/usr/bin/env bash
set -euo pipefail

action="${1:-}"
if [[ "${action}" != "archive" && "${action}" != "unarchive" ]]; then
  echo "Usage: $0 [archive|unarchive]" >&2
  exit 1
fi

if [[ -z "${CLOUDING_APIKEY:-}" || -z "${SERVER_ID:-}" ]]; then
  echo "CLOUDING_APIKEY and SERVER_ID must be set in the environment." >&2
  exit 1
fi

response=$(curl -sS -w "\n%{http_code}" -X POST "https://api.clouding.io/v1/servers/${SERVER_ID}/${action}" \
  -H "Content-Type: application/json" \
  -H "X-API-KEY: ${CLOUDING_APIKEY}")

http_code=$(echo "${response}" | tail -n 1)
body=$(echo "${response}" | sed '$d')

echo "HTTP status: ${http_code}"
echo "Response (first 200 chars):"
echo "${body}" | head -c 200
echo ""

if [[ "${http_code}" -lt 200 || "${http_code}" -ge 300 ]]; then
  echo "Clouding API request failed." >&2
  exit 1
fi
