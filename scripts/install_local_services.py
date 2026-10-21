"""Keep the local real coordinator and SSH tunnels alive with macOS launchd."""

import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
from hub.config import Config, ROOT

cfg = Config()
if (cfg.data / ".hosted-on-workstation").exists():
    raise SystemExit(
        "Coordinator moved to the workstation. Use scripts/workshop.sh services for the local preview proxy."
    )
if sys.platform != "darwin":
    raise SystemExit(
        "This installer is for macOS; see deploy/robot-hub.service for Linux."
    )
folder = Path.home() / "Library/LaunchAgents"
folder.mkdir(parents=True, exist_ok=True)
services = [
    (
        "org.example.robot-training-hub",
        [
            str(ROOT / ".venv/bin/uvicorn"),
            "hub.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
            "--no-access-log",
        ],
        {
            "HUB_DATA": str(cfg.data),
            "HUB_PUBLIC_URL": cfg.public_url,
            "HUB_DEVELOPMENT": "0",
        },
    )
]
for item in json.loads((cfg.data / "worker-connections.json").read_text()):
    name = item["name"].lower().replace(" ", "-")
    services.append(
        (
            "org.example.robot-training-hub.tunnel." + name,
            [
                "/usr/bin/ssh",
                "-N",
                "-o",
                "BatchMode=yes",
                "-o",
                "ExitOnForwardFailure=yes",
                "-o",
                "ServerAliveInterval=15",
                "-o",
                "ServerAliveCountMax=3",
                "-o",
                "ConnectTimeout=10",
                "-R",
                f"127.0.0.1:{item['port']}:127.0.0.1:8000",
                item["host"],
            ],
            {},
        )
    )
for label, args, environment in services:
    file = folder / (label + ".plist")
    log = cfg.data / (label + ".log")
    value = {
        "Label": label,
        "ProgramArguments": args,
        "WorkingDirectory": str(ROOT),
        "EnvironmentVariables": environment,
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,
        "StandardOutPath": str(log),
        "StandardErrorPath": str(log),
        "Umask": 63,
    }
    file.write_bytes(plistlib.dumps(value))
    file.chmod(0o600)
    target = f"gui/{os.getuid()}/{label}"
    subprocess.run(
        ["launchctl", "bootout", target],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        ["launchctl", "bootstrap", f"gui/{os.getuid()}", str(file)], check=True
    )
    print("Started " + label)
