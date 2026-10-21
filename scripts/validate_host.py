"""Validate frozen task configuration with an existing training interpreter; no RL launched."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile
from hub.hardware import discover
from hub.snapshots import extract_snapshot, verify

p = argparse.ArgumentParser()
p.add_argument("--training-python", required=True)
p.add_argument("--archive", type=Path, default=Path("data/validation-source.zip"))
a = p.parse_args()
root = Path("data/validation-source").resolve()
out = Path("data/validation-output").resolve()
out.mkdir(exist_ok=True, parents=True)
with zipfile.ZipFile(a.archive) as archive:
    checksum = hashlib.sha256(archive.read("manifest.json")).hexdigest()
if not root.exists():
    extract_snapshot(a.archive.read_bytes(), root, checksum)
verify(root, checksum)
env = {
    **os.environ,
    "HUB_RUN_OUTPUT": str(out),
    "PYTHONDONTWRITEBYTECODE": "1",
    "MUJOCO_GL": "disable",
}
result = subprocess.run(
    [a.training_python, "-B", str(root / "hub_launch.py"), "--validate-only"],
    env=env,
    capture_output=True,
    text=True,
    timeout=90,
)
(out / "stdout.txt").write_text(result.stdout)
(out / "stderr.txt").write_text(result.stderr)
report = {
    "returncode": result.returncode,
    "snapshot_sha256": checksum,
    "hardware": discover(),
    "task_validation": json.loads((out / "validation.json").read_text())
    if (out / "validation.json").exists()
    else None,
}
(out / "host-report.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
if result.returncode:
    print(result.stderr[-6000:])
verify(root, checksum)
raise SystemExit(result.returncode)
