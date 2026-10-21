"""Install the isolated workstation coordinator; no sudo, nginx, firewall or existing-site changes."""

import argparse
from pathlib import Path
import shlex
import subprocess
import json

p = argparse.ArgumentParser()
p.add_argument("--public-url", default="http://127.0.0.1:8000")
p.add_argument("--start", action="store_true")
a = p.parse_args()
if "\n" in a.public_url or not a.public_url.startswith(
    ("https://", "http://127.0.0.1:")
):
    p.error("Use HTTPS or a private loopback URL")
unit = Path("deploy/robot-hub-user.service").read_text()
root = "/home/operator/robot-training-hub"
env = (
    f"HUB_DATA={root}/data/workshop\nHUB_PUBLIC_URL={a.public_url}\nHUB_DEVELOPMENT=0\n"
)
payload = json.dumps({"unit": unit, "env": env, "start": a.start})
remote = """import os,pathlib,json,subprocess,sys
p=json.load(sys.stdin);root=pathlib.Path.home()/'robot-training-hub';d=root/'data';d.mkdir(exist_ok=True)
u=pathlib.Path.home()/'.config/systemd/user/robot-training-hub-coordinator.service';u.parent.mkdir(parents=True,exist_ok=True);u.write_text(p['unit'])
f=d/'coordinator.env';fd=os.open(f,os.O_CREAT|os.O_TRUNC|os.O_WRONLY,0o600)
with os.fdopen(fd,'w') as stream:stream.write(p['env'])
subprocess.run(['systemctl','--user','daemon-reload'],check=True)
if p['start']:
 assert (d/'workshop/hub.sqlite3').is_file(),'Migrate workshop data before starting'
 subprocess.run(['systemctl','--user','enable','--now','robot-training-hub-coordinator'],check=True)
 subprocess.run(['systemctl','--user','is-active','robot-training-hub-coordinator'],check=True)
"""
subprocess.run(
    [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        "operator@192.0.2.20",
        "python3 -c " + shlex.quote(remote),
    ],
    input=payload,
    text=True,
    check=True,
)
print(
    "Workstation coordinator configured on private port 8010. Existing sites unchanged."
)
