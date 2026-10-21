#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export HUB_DEVELOPMENT=1
export HUB_PUBLIC_URL="${HUB_PUBLIC_URL:-http://127.0.0.1:8000}"
uv sync --extra worker --extra test
npm ci --prefix frontend --include=dev --bin-links=true
npm run build --prefix frontend
uv run robot-hub demo
uv run uvicorn hub.app:app --host 127.0.0.1 --port 8000 &
coordinator_pid=$!
worker_pid=''
cleanup() {
  if [[ -n "$worker_pid" ]]; then kill "$worker_pid" 2>/dev/null || true; fi
  kill "$coordinator_pid" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM
for attempt in $(seq 1 30); do
  if curl -fsS "$HUB_PUBLIC_URL/api/health" >/dev/null; then break; fi
  sleep 1
done
uv run robot-hub demo-workers &
worker_pid=$!
printf '\nOpen %s and use the admin sign-in link above.\n' "$HUB_PUBLIC_URL"
wait "$coordinator_pid"
