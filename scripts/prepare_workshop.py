"""Create real workshop state once. Never seeds mock users, telemetry, or runs."""

import argparse
import json
import os
from pathlib import Path
import secrets

from hub.cli import provision_password
from hub.config import Config, DEFAULT_SERVER
from hub.db import DB, digest, now, pack, uid
from hub.motions import store_motion

p = argparse.ArgumentParser()
p.add_argument("--admin", required=True)
p.add_argument("--motion", type=Path)
a = p.parse_args()
cfg = Config()
db = DB(cfg)
if cfg.development:
    raise SystemExit("Real workshop requires HUB_DEVELOPMENT=0")
credentials = cfg.data / "admin-credentials.txt"
if not credentials.exists():
    provision_password(db, a.admin, credentials)
with db.connect() as c:
    owner = dict(
        c.execute(
            'SELECT * FROM users WHERE email=? AND role="admin"', (a.admin.lower(),)
        ).fetchone()
    )
    motion_exists = c.execute(
        "SELECT 1 FROM motions WHERE label=?", ("MJ dance · Booster K1",)
    ).fetchone()
if a.motion and not motion_exists:
    store_motion(db, owner, a.motion.read_bytes(), "MJ dance · Booster K1", 50, True)
path = cfg.data / "worker-connections.json"
if not path.exists():
    connections = []
    for name, host, home, training, reserve in [
        (
            "Coordinator host",
            "operator@192.0.2.20",
            "/home/operator",
            "/home/operator/booster-mjlab/.venv/bin/python",
            0,
        ),
        (
            "Worker A",
            "worker-a.example.edu",
            "/data/operator",
            "/data/operator/booster_mjlab/.venv/bin/python",
            46080,
        ),
        (
            "Worker B",
            "worker-b.example.edu",
            "/data/operator",
            "/data/operator/booster_mjlab/.venv/bin/python",
            46080,
        ),
    ]:
        token = secrets.token_urlsafe(40)
        key = uid()
        config = {
            **DEFAULT_SERVER,
            "max_envs": 2048,
            "max_jobs": 1,
            "reserve_mb": reserve,
            "institutional_permission": True,
            "gpu_limits": {},
            "mps_namespace": "",
        }
        with db.tx() as c:
            c.execute(
                "INSERT INTO servers(id,name,token_hash,config) VALUES(?,?,?,?)",
                (key, name, digest(token), pack(config)),
            )
        connections.append(
            {
                "id": key,
                "name": name,
                "host": host,
                "home": home,
                "training_python": training,
                "token": token,
                "port": 18000,
            }
        )
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(connections, f, indent=2)
print("Real workshop prepared at " + str(cfg.data))
print("Private admin password: " + str(credentials))
print("Only the admin account was created. Add participant emails in /admin/users.")
