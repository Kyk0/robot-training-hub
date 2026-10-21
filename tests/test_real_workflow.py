import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import enroll, heartbeat
from hub.cli import provision_password
from hub.db import pack, unpack
from hub.motions import CSV_HEADER, parse_csv
from hub.scheduler import schedule


def csv_bytes(frames=4):
    return (
        ",".join(CSV_HEADER)
        + "\n"
        + ("\n".join([",".join(map(str, [0, 0, 0.7, 0, 0, 0, 1] + [0] * 22))] * frames))
        + "\n"
    ).encode()


def test_admin_password_private_file_permissions_and_no_hash_leak(setup):
    app, db, cfg, client = setup
    path = cfg.data / "private" / "admin.txt"
    provision_password(db, "admin@example.org", path)
    password = path.read_text().split("Password: ")[1].splitlines()[0]
    assert len(password) >= 30
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        provision_password(db, "admin@example.org", path)
    c = TestClient(app)
    c.headers["X-Hub-Request"] = "1"
    assert (
        c.post(
            "/api/auth/password",
            json={"email": "admin@example.org", "password": "wrong"},
        ).status_code
        == 401
    )
    assert (
        c.post(
            "/api/auth/password",
            json={"email": "admin@example.org", "password": password},
        ).json()["redirect"]
        == "/admin"
    )
    assert "password_hash" not in c.get("/api/me").text
    assert "password_hash" not in c.get("/api/admin/users").text
    assert password not in cfg.db.read_bytes().decode("utf-8", errors="ignore")
    c.post("/api/auth/logout")
    for _ in range(8):
        assert (
            c.post(
                "/api/auth/password",
                json={"email": "admin@example.org", "password": "wrong"},
            ).status_code
            == 401
        )
    assert (
        c.post(
            "/api/auth/password",
            json={"email": "admin@example.org", "password": password},
        ).status_code
        == 429
    )


def test_csv_motion_upload_approval_ownership_and_snapshot(setup, job):
    app, db, cfg, client = setup
    alice = client("alice@example.org")
    bob = client("bob@example.org")
    admin = client("admin@example.org")
    r = alice.post(
        "/api/motions?label=Dance&shared=true&fps=50",
        content=csv_bytes(),
        headers={"Content-Type": "text/csv"},
    )
    assert r.status_code == 201, r.text
    motion = r.json()
    assert not motion["shared"] and not motion["approved"]
    key = motion["id"]
    assert bob.get(f"/api/motions/{key}/preview").status_code == 404
    assert (
        alice.get("/api/options").json()["motions"]
        == db.settings(db.connect())["motions"]
    )
    spec = {**job, "motion_id": key}
    assert alice.post("/api/runs", json=spec).status_code == 422
    assert (
        admin.post(
            f"/api/admin/motions/{key}/approve", json={"approved": True, "shared": True}
        ).status_code
        == 200
    )
    assert bob.get(f"/api/motions/{key}/preview").json()["frames"] == 4
    run = alice.post("/api/runs", json=spec)
    assert run.status_code == 201, run.text
    frozen = json.loads(
        (cfg.data / "snapshots" / run.json()["id"] / "hub_config.json").read_text()
    )
    assert frozen["motion"]["sha256"] == motion["sha256"]
    assert frozen["motion"]["artifact"] == "upload:" + key
    assert (cfg.data / "snapshots" / run.json()["id"] / "hub_motion.py").exists()
    assert (cfg.data / "motions" / key / "input.csv").stat().st_mode & 0o222 == 0


def test_csv_rejects_nan_header_and_quaternion():
    valid = csv_bytes()
    assert parse_csv(valid, 50)["duration"] == pytest.approx(0.06)
    for bad in (
        valid.replace(b"0.7", b"nan"),
        valid.replace(b"root_pos_x", b"wrong"),
        valid.replace(b"0,0,0,1,", b"0,0,0,0,"),
    ):
        with pytest.raises(ValueError):
            parse_csv(bad, 50)
    with pytest.raises(ValueError):
        parse_csv(valid, 0)


def test_global_capacity_and_future_environment_limits(setup, job):
    app, db, cfg, client = setup
    admin = client("admin@example.org")
    alice = client("alice@example.org")
    bob = client("bob@example.org")
    s = admin.get("/api/admin/settings").json()
    assert s["max_envs"] == 2048 and s["max_running_jobs"] == 10
    s["max_running_jobs"] = 1
    assert admin.put("/api/admin/settings", json=s).status_code == 200
    worker, _ = enroll(app, admin, max_jobs=10)
    heartbeat(worker, total=100000, free=100000)
    a = alice.post("/api/runs", json=job).json()
    b = bob.post("/api/runs", json=job).json()
    schedule(db)
    assert alice.get("/api/runs/" + a["id"]).json()["status"] == "STARTING"
    assert bob.get("/api/runs/" + b["id"]).json()["status"] == "QUEUED"
    assert alice.post("/api/runs/" + a["id"] + "/cancel").status_code == 200
    # STARTING capacity is retained until worker confirms cancellation.
    schedule(db)
    assert bob.get("/api/runs/" + b["id"]).json()["status"] == "QUEUED"
    assert (
        admin.post(
            "/api/admin/users/bulk",
            json={"emails": ["new@example.org"], "env_limit": 1024},
        ).status_code
        == 200
    )
    participant = next(
        u
        for u in admin.get("/api/admin/users").json()
        if u["email"] == "new@example.org"
    )
    invite = admin.post("/api/admin/users/" + participant["id"] + "/invite").json()[
        "url"
    ]
    c = TestClient(app)
    c.headers["X-Hub-Request"] = "1"
    assert (
        c.post(
            "/api/auth/verify", json={"token": invite.split("token=")[1]}
        ).status_code
        == 200
    )
    assert c.post("/api/runs", json={**job, "num_envs": 2048}).status_code == 422
    assert c.get("/api/admin/users").status_code == 403


def test_tensorboard_upload_offsets_and_access(setup, job):
    app, db, cfg, client = setup
    alice = client("alice@example.org")
    bob = client("bob@example.org")
    admin = client("admin@example.org")
    worker, _ = enroll(app, admin)
    heartbeat(worker)
    run = alice.post("/api/runs", json=job).json()
    assignment = heartbeat(worker).json()["assignments"][0]
    key = run["id"]
    header = {"X-Job-Lease": assignment["lease"]}
    assert (
        worker.post(
            f"/api/worker/runs/{key}/claim", json={"lease": assignment["lease"]}
        ).status_code
        == 200
    )
    name = "events.out.tfevents.test"
    url = f"/api/worker/runs/{key}/events?name={name}&offset=0"
    assert (
        worker.put(url, content=b"event bytes", headers=header).json()["offset"] == 11
    )
    assert worker.put(url, content=b"duplicate", headers=header).status_code == 409
    assert (cfg.data / "tensorboard" / key / name).read_bytes() == b"event bytes"
    assert (
        worker.put(
            url.replace(name, "../escape"), content=b"x", headers=header
        ).status_code
        == 422
    )
    assert bob.get(f"/api/runs/{key}/tensorboard/").status_code == 404
    assert TestClient(app).get(f"/api/runs/{key}/tensorboard/").status_code == 401
    assert alice.get(f"/api/runs/{key}").json()["tensorboard_available"]


def test_real_tensorboard_proxy_serves_scalar_data(setup, job, tmp_path):
    from tensorboard.summary.writer.event_file_writer import EventFileWriter
    from tensorboard.compat.proto.event_pb2 import Event
    from tensorboard.compat.proto.summary_pb2 import Summary
    import time

    app, db, cfg, client = setup
    admin = client("admin@example.org")
    alice = client("alice@example.org")
    worker, _ = enroll(app, admin)
    heartbeat(worker)
    run = alice.post("/api/runs", json=job).json()
    key = run["id"]
    logdir = cfg.data / "tensorboard" / key
    writer = EventFileWriter(str(logdir))
    writer.add_event(
        Event(
            wall_time=time.time(),
            step=1,
            summary=Summary(
                value=[Summary.Value(tag="Train/mean_reward", simple_value=2.5)]
            ),
        )
    )
    writer.flush()
    writer.close()
    with TestClient(app) as c:
        c.cookies.update(alice.cookies)
        r = c.get(f"/api/runs/{key}/tensorboard/")
        assert r.status_code == 200, r.text
        assert "TensorBoard" in r.text
        values = c.get(
            f"/api/runs/{key}/tensorboard/data/plugin/scalars/scalars?run=.&tag=Train%2Fmean_reward"
        )
        assert values.status_code == 200, values.text
        assert values.json()[-1][1:] == [1, 2.5]


def test_gpu_eighty_percent_ceiling_counts_external_and_starting_memory(setup, job):
    app, db, cfg, client = setup
    admin = client("admin@example.org")
    alice = client("alice@example.org")
    bob = client("bob@example.org")
    worker, server = enroll(app, admin, max_jobs=10)
    heartbeat(worker, total=100000, free=21000)
    a = alice.post("/api/runs", json=job).json()
    assert alice.get("/api/runs/" + a["id"]).json()["status"] == "QUEUED"
    # External users occupy 70%; one estimated 8.7%-sized workshop job fits.
    heartbeat(worker, total=100000, free=30000)
    assert alice.get("/api/runs/" + a["id"]).json()["status"] == "STARTING"
    b = bob.post("/api/runs", json=job).json()
    assert bob.get("/api/runs/" + b["id"]).json()["status"] == "QUEUED"
    capacity = next(
        s for s in admin.get("/api/admin/servers").json() if s["id"] == server["id"]
    )["capacity"][0]
    assert capacity["memory_percent"] == 80 and capacity["additional_jobs"] == 0
    assert capacity["minimum_free_mb"] == 20000
    settings = admin.get("/api/admin/settings").json()
    settings["gpu_memory_percent"] = 90
    admin.put("/api/admin/settings", json=settings).raise_for_status()
    schedule(db)
    first = alice.get("/api/runs/" + a["id"]).json()
    second = bob.get("/api/runs/" + b["id"]).json()
    assert first["placement"]["gpu_memory_percent"] == 80
    assert (
        second["status"] == "STARTING"
        and second["placement"]["gpu_memory_percent"] == 90
    )


def test_eighteen_participants_cannot_exceed_ten_global_jobs(setup, job):
    app, db, cfg, client = setup
    admin = client("admin@example.org")
    emails = [f"workshop{i:02}@example.org" for i in range(18)]
    admin.post(
        "/api/admin/users/bulk", json={"emails": emails, "env_limit": 2048}
    ).raise_for_status()
    worker, _ = enroll(app, admin, max_jobs=18)
    heartbeat(worker, total=1000000, free=1000000)
    for email in emails:
        assert client(email).post("/api/runs", json=job).status_code == 201
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: schedule(db), range(8)))
    with db.connect() as c:
        assert (
            c.execute("SELECT count(*) FROM jobs WHERE status='STARTING'").fetchone()[0]
            == 10
        )
        assert (
            c.execute("SELECT count(*) FROM jobs WHERE status='QUEUED'").fetchone()[0]
            == 8
        )


def test_memory_floor_keeps_stricter_shared_reservation():
    from hub.scheduler import minimum_free_mb

    assert (
        minimum_free_mb(
            {"total_mb": 100000},
            {"reserve_mb": 46080, "margin_mb": 2048, "gpu_memory_percent": 80},
        )
        == 48128
    )
    assert (
        minimum_free_mb(
            {"total_mb": 24576},
            {"reserve_mb": 0, "margin_mb": 2048, "gpu_memory_percent": 80},
        )
        == 4916
    )
