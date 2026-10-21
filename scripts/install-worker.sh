#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ $# -ne 1 ]]; then printf 'Usage: %s /absolute/existing/booster-mjlab/.venv/bin/python\n' "$0"; exit 2; fi
training_python="$1"
[[ "$training_python" = /* && -x "$training_python" ]] || { echo 'Existing executable training interpreter required'; exit 2; }
uv sync --frozen --extra worker
mkdir -p data
chmod 700 data
if [[ ! -f data/worker.env ]]; then
  {
    printf 'HUB_COORDINATOR=https://hub.example.edu\n'
    printf 'HUB_WORKER_ROOT=%s/data/runs\n' "$PWD"
    printf 'HUB_TRAINING_PYTHON=%s\n' "$training_python"
    printf 'HUB_WORKER_TOKEN_FILE=%s/data/worker.token\n' "$PWD"
    printf 'MUJOCO_GL=disable\n'
  } > data/worker.env
  chmod 600 data/worker.env
fi
printf 'Worker dependencies installed. Edit data/worker.env, enroll host in admin panel, and save its token in data/worker.token (chmod 600).\n'
printf 'Launch: set -a; source data/worker.env; set +a; .venv/bin/robot-worker\n'
