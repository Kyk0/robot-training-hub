#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -e vendor/booster_mjlab/.git ]]; then
  git clone https://github.com/IntelligentRoboticsLab/booster_mjlab.git vendor/booster_mjlab
  git -C vendor/booster_mjlab checkout d92e11395d961096d639446c0a8a176f12bb51da
fi
if [[ ! -e vendor/mjlab/.git ]]; then
  git init vendor/mjlab
  git -C vendor/mjlab remote add origin https://github.com/mujocolab/mjlab.git
  git -C vendor/mjlab fetch --depth 1 origin b517e0c489139e7fcee95702cfb2b01931264985
  git -C vendor/mjlab checkout FETCH_HEAD
fi
uv sync --frozen --extra worker --extra test
npm ci --prefix frontend --include=dev --bin-links=true
npm run build --prefix frontend
