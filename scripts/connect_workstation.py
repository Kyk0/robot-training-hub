"""Connect localhost:8000 to the workstation-hosted backend; no local coordinator runs."""

import os
from pathlib import Path
import plistlib
import subprocess
import sys

if sys.platform != "darwin":
    raise SystemExit(
        "On Linux use ssh -N -L 127.0.0.1:8000:127.0.0.1:8010 operator@192.0.2.20"
    )
root = Path(__file__).resolve().parents[1]
label = "org.example.robot-training-hub.proxy"
folder = Path.home() / "Library/LaunchAgents"
folder.mkdir(exist_ok=True, parents=True)
log = root / "data/workshop-proxy.log"
target = f"gui/{os.getuid()}"
unit = {
    "Label": label,
    "ProgramArguments": [
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
        "-L",
        "127.0.0.1:8000:127.0.0.1:8010",
        "operator@192.0.2.20",
    ],
    "RunAtLoad": True,
    "KeepAlive": True,
    "ThrottleInterval": 10,
    "StandardOutPath": str(log),
    "StandardErrorPath": str(log),
}
file = folder / (label + ".plist")
file.write_bytes(plistlib.dumps(unit))
file.chmod(0o600)
subprocess.run(
    ["launchctl", "bootout", target + "/" + label],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
subprocess.run(["launchctl", "bootstrap", target, str(file)], check=True)
print("Local preview forwards to the workstation backend at http://127.0.0.1:8000")
