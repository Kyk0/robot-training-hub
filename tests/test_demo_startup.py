"""Regression: a failed coordinator must not launch workers or claim readiness."""

import os
from pathlib import Path
import shutil
import subprocess


def test_demo_refuses_to_start_workers_when_coordinator_exits(tmp_path):
    root = Path(__file__).resolve().parents[1]
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copyfile(root / "scripts/demo.sh", scripts / "demo.sh")
    commands = tmp_path / "commands"
    commands.mkdir()
    venv = tmp_path / ".venv/bin"
    venv.mkdir(parents=True)
    for name in ("uv", "npm"):
        file = commands / name
        file.write_text("#!/bin/sh\nexit 0\n")
        file.chmod(0o755)
    curl = commands / "curl"
    curl.write_text("#!/bin/sh\nexit 7\n")
    curl.chmod(0o755)
    coordinator = venv / "uvicorn"
    coordinator.write_text("#!/bin/sh\nexit 17\n")
    coordinator.chmod(0o755)
    worker = venv / "robot-hub"
    worker.write_text('#!/bin/sh\ntouch "$PWD/workers-started"\n')
    worker.chmod(0o755)
    result = subprocess.run(
        ["bash", str(scripts / "demo.sh")],
        env={**os.environ, "PATH": str(commands) + os.pathsep + os.environ["PATH"]},
        capture_output=True,
        text=True,
        timeout=6,
    )
    assert result.returncode != 0
    assert "Coordinator failed to start" in result.stderr
    assert "is ready:" not in result.stdout
    assert not (tmp_path / "workers-started").exists()
