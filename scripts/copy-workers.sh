#!/usr/bin/env bash
# Explicit user-owned workshop destinations only. Runtime data and secrets stay on their host.
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/python scripts/package_release.py
for host in worker-a.example.edu worker-b.example.edu operator@192.0.2.20; do
  printf 'Copying platform source and built website to %s:~/robot-training-hub\n' "$host"
  ssh -o BatchMode=yes -o ConnectTimeout=10 "$host" 'mkdir -p ~/robot-training-hub && tar -xzf - -C ~/robot-training-hub' < data/platform-release.tar.gz
done
