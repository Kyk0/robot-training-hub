#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export HUB_DEVELOPMENT=0
export HUB_DATA="${HUB_DATA:-$PWD/data/workshop}"
export HUB_PUBLIC_URL="${HUB_PUBLIC_URL:-http://127.0.0.1:8000}"
case "${1:-serve}" in
  serve|connect) exec ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 -L 127.0.0.1:8000:127.0.0.1:8010 operator@192.0.2.20 ;;
  services) exec .venv/bin/python scripts/connect_workstation.py ;;
  coordinator-restart) exec ssh operator@192.0.2.20 systemctl --user restart robot-training-hub-coordinator ;;
  workers) exec .venv/bin/python scripts/install_real_workers.py ;;
  prepare) shift; exec .venv/bin/python scripts/prepare_workshop.py "$@" ;;
  *) printf 'Usage: %s [serve|services|workers|prepare --admin EMAIL --motion CSV]\n' "$0" >&2; exit 2 ;;
esac
