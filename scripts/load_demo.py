"""Submit 18 demo users through real authenticated HTTP requests. No bypass API."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import httpx
from hub.cli import login_link
from hub.config import Config
from hub.db import DB

p = argparse.ArgumentParser()
p.add_argument("--iterations", type=int, default=200)
p.add_argument("--url", default="http://127.0.0.1:8000")
args = p.parse_args()
cfg = Config()
if not cfg.development:
    raise SystemExit("HUB_DEVELOPMENT=1 required")
db = DB(cfg)


def submit(i):
    email = f"participant{i:02}@workshop.example"
    token = login_link(db, email).split("token=")[1]
    with httpx.Client(
        base_url=args.url, headers={"X-Hub-Request": "1"}, timeout=120
    ) as c:
        r = c.post("/api/auth/verify", json={"token": token})
        r.raise_for_status()
        r = c.post(
            "/api/runs",
            json={
                "name": f"Walking exploration {i:02}",
                "motion_id": "demo-walk",
                "num_envs": 512,
                "iterations": args.iterations,
            },
            timeout=120,
        )
        if r.status_code == 409:
            return {"email": email, "result": "Already has outstanding job"}
        r.raise_for_status()
        return {"email": email, "id": r.json()["id"], "status": r.json()["status"]}


with ThreadPoolExecutor(max_workers=6) as pool:
    for result in pool.map(submit, range(1, 19)):
        print(result)
