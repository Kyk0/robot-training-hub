"""Verify the running demo over HTTP and save a credential-free validation summary."""

import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import time
import zipfile
import httpx
from hub.cli import login_link
from hub.config import Config
from hub.db import DB

p = argparse.ArgumentParser()
p.add_argument("--url", default="http://127.0.0.1:8000")
p.add_argument("--wait", type=int, default=60)
a = p.parse_args()
cfg = Config()
if not cfg.development:
    raise SystemExit("HUB_DEVELOPMENT=1 required")
token = login_link(DB(cfg), "admin@workshop.example").split("token=")[1]
with httpx.Client(base_url=a.url, headers={"X-Hub-Request": "1"}, timeout=120) as c:
    c.post("/api/auth/verify", json={"token": token}).raise_for_status()
    deadline = time.monotonic() + a.wait
    while True:
        response = c.get("/api/runs")
        response.raise_for_status()
        runs = response.json()
        counts = Counter(r["status"] for r in runs)
        if (
            not any(counts.get(s) for s in ["QUEUED", "STARTING", "RUNNING"])
            or time.monotonic() >= deadline
        ):
            break
        time.sleep(2)
    assert len({r["user_id"] for r in runs}) >= 18, (
        "Expected eighteen submitting participants"
    )
    assert counts.get("COMPLETED") == len(runs), counts
    run = next(r for r in runs if r["status"] == "COMPLETED")
    detail = c.get("/api/runs/" + run["id"]).json()
    assert (
        detail["iteration"] == detail["spec"]["iterations"]
        and detail["execution"]["mock"]
    )
    assert detail["metrics"], "No live reward samples recorded"
    logs = c.get("/api/runs/" + run["id"] + "/logs/download")
    logs.raise_for_status()
    assert "HUB_METRIC" in logs.text
    source = c.get("/api/code/" + run["id"] + "/download")
    source.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(source.content)) as archive:
        raw = archive.read("manifest.json")
        manifest = json.loads(raw)
        assert hashlib.sha256(raw).hexdigest() == detail["snapshot"]
        for name, checksum in manifest["files"].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == checksum
    checkpoint = next(
        item for item in detail["artifacts"] if "mock_checkpoint_" in item["path"]
    )
    result = c.get(
        "/api/runs/" + run["id"] + "/artifacts", params={"path": checkpoint["path"]}
    )
    result.raise_for_status()
    assert result.json()["mock"]
    for path in [
        "/login",
        "/register",
        "/dashboard",
        "/train/new",
        "/runs",
        "/code",
        "/admin",
        "/admin/runs",
        "/admin/servers",
        "/admin/users",
        "/admin/settings",
    ]:
        response = c.get(path)
        assert response.status_code == 200 and "Robot Training Hub" in response.text
    summary = {
        "participants_submitted": len({r["user_id"] for r in runs}),
        "total_runs": len(runs),
        "statuses": dict(counts),
        "sample_run": run["id"],
        "source_zip_bytes": len(source.content),
        "verified_source_files": len(manifest["files"]),
        "sample_reward_points": len(detail["metrics"]),
        "checkpoint_download_verified": True,
        "logs_download_verified": True,
        "frontend_routes_served": True,
        "mode": "MOCK — no GPU training",
    }
Path("docs/validation/mock-summary.json").write_text(
    json.dumps(summary, indent=2) + "\n"
)
print(json.dumps(summary, indent=2))
