"""Install user-owned workers on the three authorized hosts, without touching training checkouts."""

import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
from hub.config import Config

cfg = Config()
for item in json.loads((cfg.data / "worker-connections.json").read_text()):
    home = item["home"]
    root = home + "/robot-training-hub"
    runtime = root + "/data/workshop-worker"
    unit = "\n".join(
        [
            "[Unit]",
            "Description=Robot Training Hub GPU worker",
            "After=network-online.target",
            "",
            "[Service]",
            "Type=simple",
            "WorkingDirectory=" + root,
            "Environment=MUJOCO_GL=disable",
            "Environment=OMP_NUM_THREADS=4",
            "Environment=PYTHONUNBUFFERED=1",
            "ExecStart="
            + shlex.join(
                [
                    root + "/.venv/bin/python",
                    "-m",
                    "hub.worker",
                    "--coordinator",
                    item.get("coordinator", "http://127.0.0.1:" + str(item["port"])),
                    "--token-file",
                    runtime + "/worker.token",
                    "--root",
                    runtime + "/runs",
                    "--training-python",
                    item["training_python"],
                ]
            ),
            "Restart=on-failure",
            "RestartSec=5",
            "TimeoutStopSec=60",
            "KillMode=process",
            "UMask=0077",
            "",
            "[Install]",
            "WantedBy=default.target",
            "",
        ]
    )
    # Payload travels through the encrypted SSH stdin, never the process arguments or logs.
    payload = json.dumps({"runtime": runtime, "token": item["token"], "unit": unit})
    remote = """import json,os,pathlib,subprocess,sys
p=json.load(sys.stdin);d=pathlib.Path(p['runtime']);d.mkdir(parents=True,exist_ok=True,mode=0o700)
t=d/'worker.token';fd=os.open(t,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
with os.fdopen(fd,'w') as f:f.write(p['token'])
u=pathlib.Path.home()/'.config/systemd/user/robot-training-hub-worker.service';u.parent.mkdir(parents=True,exist_ok=True);u.write_text(p['unit'])
subprocess.run(['systemctl','--user','daemon-reload'],check=True)
state=subprocess.check_output(['systemctl','--user','show','-p','LoadState','--value','robot-training-hub-worker.service'],text=True).strip()
if state=='not-found':
    # University LDAP home and interactive $HOME can differ. The runtime user
    # unit directory is shared with the manager and requires no root changes.
    subprocess.run(['systemctl','--user','link','--runtime',str(u)],check=True)
    subprocess.run(['systemctl','--user','daemon-reload'],check=True)
    subprocess.run(['systemctl','--user','enable','--runtime','--now','robot-training-hub-worker.service'],check=True)
    print('Runtime user-service link: rerun workshop.sh workers after a host reboot.')
else:
    subprocess.run(['systemctl','--user','enable','--now','robot-training-hub-worker.service'],check=True)
subprocess.run(['systemctl','--user','is-active','robot-training-hub-worker.service'],check=True)
"""
    subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            item["host"],
            "python3 -c " + shlex.quote(remote),
        ],
        input=payload,
        text=True,
        check=True,
    )
    print(
        item["name"]
        + ": real worker installed (user service, existing training interpreter)"
    )
