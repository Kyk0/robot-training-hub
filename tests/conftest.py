import json
from pathlib import Path
import subprocess
import pytest
from fastapi.testclient import TestClient
from hub.app import create_app
from hub.config import Config, DEFAULT_SERVER
from hub.db import DB, digest, now, pack, uid
from hub.cli import add_admin, login_link


@pytest.fixture
def setup(tmp_path):
    repos = []
    for name in ("booster", "mjlab"):
        root = tmp_path / name
        root.mkdir()
        (root / "src").mkdir()
        (root / "src/example.py").write_text("REWARD = 1\n")
        (root / "pyproject.toml").write_text(
            '[project]\nname="fixture"\nversion="0.0.0"\n'
        )
        for args in (
            ["init", "-q"],
            ["add", "."],
            [
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.org",
                "commit",
                "-qm",
                "fixture",
            ],
        ):
            subprocess.run(["git", "-C", str(root), *args], check=True)
        repos.append(root)
    cfg = Config(
        data=tmp_path / "data",
        base_repo=repos[0],
        mjlab_repo=repos[1],
        development=True,
    )
    app = create_app(cfg)
    db = app.state.db
    add_admin(db, "admin@example.org")
    with db.tx() as c:
        for email in ("alice@example.org", "bob@example.org"):
            c.execute(
                "INSERT INTO users(id,email,approved,created) VALUES(?,?,1,?)",
                (uid(), email, now()),
            )
        s = db.settings(c)
        s["motions"] = [
            {
                "id": "walk",
                "label": "Walk",
                "artifact": "demo/motions/walk:v0",
                "sha256": None,
            }
        ]
        c.execute("UPDATE settings SET value=?", (pack(s),))

    def client(email):
        cl = TestClient(app)
        cl.headers["X-Hub-Request"] = "1"
        token = login_link(db, email).split("token=")[1]
        assert cl.post("/api/auth/verify", json={"token": token}).status_code == 200
        return cl

    return app, db, cfg, client


@pytest.fixture
def job():
    return {
        "name": "Walking experiment",
        "motion_id": "walk",
        "num_envs": 512,
        "iterations": 20,
    }


def enroll(app, admin, **overrides):
    cfg = {
        **DEFAULT_SERVER,
        "institutional_permission": True,
        "reserve_mb": 0,
        "max_jobs": 2,
        "gpu_limits": {},
        "mps_namespace": "",
        **overrides,
    }
    response = admin.post("/api/admin/servers", json={"name": uid(), "config": cfg})
    assert response.status_code == 201, response.text
    data = response.json()
    cl = TestClient(app)
    cl.headers["Authorization"] = "Bearer " + data["token"]
    return cl, data


def heartbeat(worker, boot="boot1", total=24576, free=24576, active=None, **inventory):
    return worker.post(
        "/api/worker/heartbeat",
        json={
            "boot_id": boot,
            "inventory": {
                "gpus": [
                    {
                        "uuid": "GPU-test",
                        "name": "Test GPU",
                        "total_mb": total,
                        "free_mb": free,
                        "utilization": 0,
                        "driver": "test",
                    }
                ],
                **inventory,
            },
            "active": active or [],
        },
    )
