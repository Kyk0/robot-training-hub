#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export HUB_DEVELOPMENT=0
export HUB_DATA="${HUB_DATA:-$PWD/data/workshop}"
export HUB_PUBLIC_URL="${HUB_PUBLIC_URL:-http://127.0.0.1:8000}"
case "${1:-serve}" in
  serve) exec .venv/bin/uvicorn hub.app:app --host 127.0.0.1 --port 8000 ;;
  services) exec .venv/bin/python scripts/install_local_services.py ;;
  workers) exec .venv/bin/python scripts/install_real_workers.py ;;
  prepare) shift; exec .venv/bin/python scripts/prepare_workshop.py "$@" ;;
  *) printf 'Usage: %s [serve|services|workers|prepare --admin EMAIL --motion CSV]\n' "$0" >&2; exit 2 ;;
esac
