"""Attach the verified public endpoint to the coordinator and existing workers.
The HTTPS endpoint must already exist. No nginx, DNS, firewall or MPS changes.
"""

import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
from urllib.parse import urlsplit
import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url", required=True)
    args = p.parse_args()
    url = args.url.rstrip("/")
    parts = urlsplit(url)
    if (
        parts.scheme != "https"
        or parts.username
        or parts.password
        or parts.path
        or parts.query
        or parts.fragment
    ):
        p.error("Use a trusted HTTPS origin, without a path or credentials")
    credential_file = ROOT / "data/workshop/admin-credentials.txt"
    values = dict(
        line.split(": ", 1)
        for line in credential_file.read_text().splitlines()
        if ": " in line
    )

    def connect():
        c = httpx.Client(base_url=url, headers={"X-Hub-Request": "1"}, timeout=45)
        c.post(
            "/api/auth/password",
            json={"email": values["Email"], "password": values["Password"]},
        ).raise_for_status()
        return c

    health = httpx.get(url + "/api/health", timeout=30)
    health.raise_for_status()
    if (
        health.json().get("name") != "Robot Training Hub"
        or health.json().get("development") is not False
    ):
        raise SystemExit("The endpoint is not the production workshop")
    if httpx.get(url + "/api/admin/users", timeout=30).status_code != 401:
        raise SystemExit("Anonymous admin access must be denied")
    client = connect()
    original = client.get("/api/admin/settings").json()
    client.put(
        "/api/admin/settings", json={**original, "paused": True}
    ).raise_for_status()
    connections = json.loads(
        (ROOT / "data/workshop/worker-connections.json").read_text()
    )
    success = False
    try:
        jobs = client.get("/api/runs").json()
        if any(j["status"] in ("STARTING", "RUNNING") for j in jobs):
            raise RuntimeError(
                "Wait for running jobs before switching worker connections"
            )
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/install_workstation_coordinator.py"),
                "--public-url",
                url,
            ],
            cwd=ROOT,
            check=True,
        )
        subprocess.run(
            [
                "ssh",
                "operator@192.0.2.20",
                "systemctl --user restart robot-training-hub-coordinator",
            ],
            check=True,
        )
        for attempt in range(30):
            try:
                if httpx.get(url + "/api/health", timeout=5).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)
        else:
            raise RuntimeError("Coordinator did not restart")
        client.close()
        client = connect()
        assert any(
            cookie.name == "hub_session" and cookie.secure
            for cookie in client.cookies.jar
        ), "Public session cookie must be Secure"
        for item in connections:
            coordinator = (
                "http://127.0.0.1:8010" if item["name"] == "Coordinator host" else url
            )
            payload = json.dumps({"url": coordinator})
            remote = """import json,pathlib,shlex,subprocess,sys
p=json.load(sys.stdin);file=pathlib.Path.home()/'.config/systemd/user/robot-training-hub-worker.service'
text=file.read_text();lines=text.splitlines();found=False
for i,line in enumerate(lines):
 if line.startswith('ExecStart='):
  args=shlex.split(line[len('ExecStart='):]);assert 'hub.worker' in args and '--mock' not in args
  index=args.index('--coordinator')+1;args[index]=p['url'];lines[i]='ExecStart='+shlex.join(args);found=True
assert found,'Unexpected worker unit'
file.write_text('\\n'.join(lines)+'\\n')
subprocess.run(['systemctl','--user','daemon-reload'],check=True)
subprocess.run(['systemctl','--user','restart','robot-training-hub-worker'],check=True)
subprocess.run(['systemctl','--user','is-active','robot-training-hub-worker'],check=True)
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
            item["coordinator"] = coordinator
            print(
                item["name"] + ": direct coordinator connection configured", flush=True
            )
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            servers = client.get("/api/admin/servers").json()
            if len(servers) == len(connections) and all(
                s["online"] and not s["quarantined"] for s in servers
            ):
                # Wait for fresh heartbeats from each restarted worker, not stale inventory.
                time.sleep(6)
                servers = client.get("/api/admin/servers").json()
                if all(s["online"] and not s["quarantined"] for s in servers):
                    success = True
                    break
            time.sleep(2)
        if not success:
            raise RuntimeError(
                "Some direct workers did not reconnect; queue will remain paused"
            )
        path = ROOT / "data/workshop/worker-connections.json"
        path.write_text(json.dumps(connections, indent=2))
        path.chmod(0o600)
        (ROOT / "public-site/site-config.js").write_text(
            "// Public URL only; sign-in stays on the workstation.\nwindow.WORKSHOP = "
            + json.dumps({"url": url, "ready": True})
            + ";\n"
        )
        (ROOT / "data/workshop-public-url.txt").write_text(url + "\n")
        credential_file.write_text(
            "\n".join(
                "URL: " + url + "/login" if line.startswith("URL: ") else line
                for line in credential_file.read_text().splitlines()
            )
            + "\n"
        )
        credential_file.chmod(0o600)
        print("Public login, secure cookies, and direct workers verified.", flush=True)
    finally:
        if success:
            client.put("/api/admin/settings", json=original).raise_for_status()
        else:
            print(
                "Activation interrupted. Queue remains paused for inspection; no active training was stopped.",
                flush=True,
            )
        client.close()


if __name__ == "__main__":
    main()
