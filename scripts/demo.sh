#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export HUB_DEVELOPMENT=1
export HUB_PUBLIC_URL="${HUB_PUBLIC_URL:-http://127.0.0.1:8000}"
uv sync --frozen --extra worker --extra test
npm ci --prefix frontend --include=dev --bin-links=true
npm run build --prefix frontend

coordinator_pid=''
worker_pid=''
cleanup() {
  # Signal the Python processes directly, not an intermediate uv wrapper.
  if [[ -n "$worker_pid" ]]; then
    kill -TERM "$worker_pid" 2>/dev/null || true
    wait "$worker_pid" 2>/dev/null || true
  fi
  if [[ -n "$coordinator_pid" ]]; then
    kill -TERM "$coordinator_pid" 2>/dev/null || true
    wait "$coordinator_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

.venv/bin/uvicorn hub.app:app --host 127.0.0.1 --port 8000 --no-access-log &
coordinator_pid=$!
ready=0
for attempt in $(seq 1 30); do
  if ! kill -0 "$coordinator_pid" 2>/dev/null; then
    printf '\nCoordinator failed to start. Check the error above; port 8000 may already be in use.\n' >&2
    exit 1
  fi
  if curl --fail --silent --max-time 1 "$HUB_PUBLIC_URL/api/health" >/dev/null; then
    ready=1
    break
  fi
  sleep 1
done
if [[ "$ready" -ne 1 ]]; then
  printf '\nCoordinator did not become ready at %s. Mock workers were not started.\n' "$HUB_PUBLIC_URL" >&2
  exit 1
fi

# Print a login link only after the coordinator is actually reachable.
.venv/bin/robot-hub demo
.venv/bin/robot-hub demo-workers &
worker_pid=$!
printf '\nRobot Training Hub is ready: %s\nKeep this Terminal open while testing. Press Ctrl+C to stop.\n' "$HUB_PUBLIC_URL"
wait "$coordinator_pid"
