from concurrent.futures import ThreadPoolExecutor
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import zipfile
import pytest
from fastapi.testclient import TestClient
from hub.app import create_app
from hub.db import digest, now, pack, uid, unpack
from hub.cli import login_link
from hub.scheduler import schedule
from hub.snapshots import create_snapshot, verify, extract_snapshot, zip_tree
from hub.hardware import mps_environment
from conftest import enroll, heartbeat


def test_registration_allowlist_single_use_auth(setup):
    app, db, cfg, client = setup
    c = TestClient(app)
    c.headers["X-Hub-Request"] = "1"
    assert (
        c.post("/api/auth/register", json={"email": "new@example.org"}).status_code
        == 200
    )
    assert (
        c.post("/api/auth/request", json={"email": "new@example.org"}).status_code
        == 200
    )
    assert not list((cfg.data / "mail").glob("*"))
    admin = client("admin@example.org")
    assert (
        admin.post("/api/admin/users", json={"email": "new@example.org"}).status_code
        == 200
    )
    assert (
        c.post("/api/auth/request", json={"email": "new@example.org"}).status_code
        == 200
    )
    mail = json.loads(next((cfg.data / "mail").glob("*.json")).read_text())
    token = mail["url"].split("token=")[1]
    response = c.post("/api/auth/verify", json={"token": token})
    assert response.status_code == 200
    assert "HttpOnly" in response.headers["set-cookie"]
    assert c.post("/api/auth/verify", json={"token": token}).status_code == 400
    assert c.get("/api/me").json()["verified"] == 1
    assert c.post("/api/auth/logout").status_code == 200
    assert c.get("/api/me").status_code == 401


def test_expired_link_and_disabled_account(setup):
    app, db, cfg, client = setup
    token = login_link(db, "alice@example.org").split("token=")[1]
    with db.tx() as c:
        c.execute("UPDATE magic SET expires=0 WHERE hash=?", (digest(token),))
    c = TestClient(app)
    c.headers["X-Hub-Request"] = "1"
    assert c.post("/api/auth/verify", json={"token": token}).status_code == 400
    alice = client("alice@example.org")
    admin = client("admin@example.org")
    user = alice.get("/api/me").json()
    admin.put(
        "/api/admin/users/" + user["id"],
        json={"approved": False, "role": "participant", "env_limit": None},
    )
    assert alice.get("/api/me").status_code == 401


def test_role_permissions_and_ownership(setup, job):
    app, db, cfg, client = setup
    alice = client("alice@example.org")
    bob = client("bob@example.org")
    admin = client("admin@example.org")
    key = alice.post("/api/runs", json=job).json()["id"]
    for path in (
        "/api/admin/users",
        "/api/admin/servers",
        "/api/admin/settings",
        "/api/admin/overview",
    ):
        assert alice.get(path).status_code == 403
    for path in (
        f"/api/runs/{key}",
        f"/api/runs/{key}/logs",
        f"/api/code/{key}/tree",
        f"/api/code/{key}/download",
        f"/api/runs/{key}/artifacts?path=execution.json",
    ):
        assert bob.get(path).status_code == 404
        if "artifacts?" not in path:
            assert admin.get(path).status_code == 200
    assert bob.post(f"/api/runs/{key}/cancel").status_code == 404
    assert TestClient(app).get("/api/runs").status_code == 401
    assert (
        TestClient(app)
        .post("/api/auth/request", json={"email": "alice@example.org"})
        .status_code
        == 403
    )
    assert (
        alice.post(
            "/api/runs", json=job, headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )


def test_one_outstanding_and_cancellation(setup, job):
    app, db, cfg, client = setup
    alice = client("alice@example.org")
    r = alice.post("/api/runs", json=job)
    assert r.status_code == 201
    assert alice.post("/api/runs", json=job).status_code == 409
    key = r.json()["id"]
    assert alice.post(f"/api/runs/{key}/cancel").status_code == 200
    assert alice.get("/api/runs/" + key).json()["status"] == "CANCELED"
    assert alice.post("/api/runs", json=job).status_code == 201


def test_concurrent_submissions_database_constraint(setup, job):
    app, db, cfg, client = setup
    alice = client("alice@example.org")
    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(
            pool.map(lambda _: alice.post("/api/runs", json=job).status_code, range(8))
        )
    assert codes.count(201) == 1
    assert codes.count(409) == 7
    with db.connect() as c:
        assert c.execute("SELECT count(*) FROM jobs").fetchone()[0] == 1


def test_capacity_reservation_concurrency_and_best_fit(setup, job):
    app, db, cfg, client = setup
    admin = client("admin@example.org")
    alice = client("alice@example.org")
    bob = client("bob@example.org")
    worker, server = enroll(app, admin, reserve_mb=46080, max_jobs=3)
    heartbeat(worker, total=95830, free=52000)
    a = alice.post("/api/runs", json=job).json()
    assert (
        alice.get("/api/runs/" + a["id"]).json()["status"] == "QUEUED"
    )  # can't consume reserve
    heartbeat(worker, total=95830, free=70000)
    a = alice.get("/api/runs/" + a["id"]).json()
    assert a["status"] == "STARTING"
    b = bob.post("/api/runs", json=job).json()
    assert bob.get("/api/runs/" + b["id"]).json()["status"] == "STARTING"
    with db.connect() as c:
        active = c.execute(
            "SELECT sum(estimated_mb) FROM jobs WHERE status='STARTING'"
        ).fetchone()[0]
        assert active <= 70000 - 46080 - 2048


def test_per_gpu_limits_and_disabled_hosts(setup, job):
    app, db, cfg, client = setup
    admin = client("admin@example.org")
    alice = client("alice@example.org")
    worker, server = enroll(
        app,
        admin,
        gpu_limits={
            "GPU-test": {
                "reserve_mb": 22000,
                "margin_mb": 2048,
                "max_jobs": 1,
                "max_envs": 256,
            }
        },
    )
    heartbeat(worker)
    key = alice.post("/api/runs", json=job).json()["id"]
    assert alice.get("/api/runs/" + key).json()["status"] == "QUEUED"
    row = admin.get("/api/admin/servers").json()[0]
    row["config"]["gpu_limits"] = {}
    row["config"]["enabled"] = False
    admin.put("/api/admin/servers/" + server["id"], json=row["config"])
    schedule(db)
    assert alice.get("/api/runs/" + key).json()["status"] == "QUEUED"


def test_resource_best_fit_and_slurm_policy(setup, job):
    app, db, cfg, client = setup
    admin = client("admin@example.org")
    alice = client("alice@example.org")
    small, s = enroll(app, admin)
    big, b = enroll(app, admin)
    heartbeat(small, total=24576, free=24576, institutional_scheduler=True)
    heartbeat(big, total=95830, free=95830)
    key = alice.post("/api/runs", json=job).json()["id"]
    assert alice.get("/api/runs/" + key).json()["server_id"] == b["id"]
    alice.post(
        "/api/runs/" + key + "/cancel"
    )  # starting cancellation retains slot until ack
    cfg_small = admin.get("/api/admin/servers").json()
    small_config = next(x["config"] for x in cfg_small if x["id"] == s["id"])
    small_config["mode"] = "slurm"
    admin.put("/api/admin/servers/" + s["id"], json=small_config)
    heartbeat(small, boot="boot1", institutional_scheduler=True, slurm_job_id="1234")
    bob = client("bob@example.org")
    key = bob.post("/api/runs", json=job).json()["id"]
    assert bob.get("/api/runs/" + key).json()["server_id"] == s["id"]


def test_server_failure_restart_no_duplicate_and_claim_once(setup, job):
    app, db, cfg, client = setup
    admin = client("admin@example.org")
    alice = client("alice@example.org")
    worker, server = enroll(app, admin, max_jobs=1)
    heartbeat(worker)
    key = alice.post("/api/runs", json=job).json()["id"]
    assignment = heartbeat(worker).json()["assignments"][0]
    assert (
        worker.post(
            "/api/worker/runs/" + key + "/claim", json={"lease": assignment["lease"]}
        ).status_code
        == 200
    )
    assert (
        worker.post(
            "/api/worker/runs/" + key + "/claim", json={"lease": assignment["lease"]}
        ).status_code
        == 409
    )
    # Coordinator restart uses the same DB, retaining job lease and assignment.
    restarted = create_app(cfg)
    with db.tx() as c:
        c.execute("UPDATE servers SET last_seen=0")
    schedule(restarted.state.db)
    assert alice.get("/api/runs/" + key).json()["status"] == "STARTING"
    h = heartbeat(worker, boot="new-worker")
    assert h.json()["quarantined"] is True
    assert admin.post("/api/admin/runs/" + key + "/retry").status_code == 409
    assert (
        admin.post(
            "/api/admin/servers/" + server["id"] + "/reconcile", json={}
        ).status_code
        == 422
    )
    assert (
        admin.post(
            "/api/admin/servers/" + server["id"] + "/reconcile",
            json={"confirmed_all_processes_stopped": True},
        ).status_code
        == 200
    )
    assert alice.get("/api/runs/" + key).json()["status"] == "FAILED"
    assert admin.post("/api/admin/runs/" + key + "/retry").status_code == 201


def test_report_cancellation_logs_metrics_and_artifact(setup, job):
    app, db, cfg, client = setup
    admin = client("admin@example.org")
    alice = client("alice@example.org")
    worker, server = enroll(app, admin)
    heartbeat(worker)
    key = alice.post("/api/runs", json=job).json()["id"]
    assignment = heartbeat(worker).json()["assignments"][0]
    lease = assignment["lease"]
    worker.post("/api/worker/runs/" + key + "/claim", json={"lease": lease})
    body = {
        "lease": lease,
        "status": "RUNNING",
        "iteration": 3,
        "metrics": {"reward": 1.5},
        "logs": "iteration 3\n",
        "log_seq": 1,
        "execution": {"mock": True},
    }
    assert (
        worker.post("/api/worker/runs/" + key + "/report", json=body).status_code == 200
    )
    worker.post("/api/worker/runs/" + key + "/report", json=body)
    assert alice.get("/api/runs/" + key + "/logs").json()["text"] == "iteration 3\n"
    assert (
        worker.put(
            "/api/worker/runs/" + key + "/artifact?path=checkpoint.json",
            headers={"X-Job-Lease": lease},
            content=b'{"mock":true}',
        ).status_code
        == 200
    )
    assert (
        worker.put(
            "/api/worker/runs/" + key + "/artifact?path=checkpoint.json",
            headers={"X-Job-Lease": lease},
            content=b"changed",
        ).status_code
        == 409
    )
    assert (
        worker.put(
            "/api/worker/runs/" + key + "/artifact?path=../bad.json",
            headers={"X-Job-Lease": lease},
            content=b"{}",
        ).status_code
        == 400
    )
    alice.post("/api/runs/" + key + "/cancel")
    assert worker.post("/api/worker/runs/" + key + "/report", json=body).json()[
        "cancel"
    ]
    body["status"] = "CANCELED"
    worker.post("/api/worker/runs/" + key + "/report", json=body)
    run = alice.get("/api/runs/" + key).json()
    assert run["status"] == "CANCELED"
    assert run["metrics"][0]["reward"] == 1.5
    assert (
        alice.get("/api/runs/" + key + "/artifacts?path=checkpoint.json").content
        == b'{"mock":true}'
    )
    assert alice.post("/api/runs", json=job).status_code == 201


def test_env_controls_future_jobs_and_approved_parameters(setup, job):
    app, db, cfg, client = setup
    admin = client("admin@example.org")
    alice = client("alice@example.org")
    s = admin.get("/api/admin/settings").json()
    s["max_envs"] = 1024
    s["presets"] = [256, 512, 1024]
    s["default_envs"] = 512
    assert admin.put("/api/admin/settings", json=s).status_code == 200
    assert alice.post("/api/runs", json={**job, "num_envs": 2048}).status_code == 422
    assert (
        alice.post(
            "/api/runs", json={**job, "rewards": {"unknown_reward": 5}}
        ).status_code
        == 422
    )
    assert alice.post("/api/runs", json={**job, "learning_rate": 10}).status_code == 422
    user = alice.get("/api/me").json()
    admin.put(
        "/api/admin/users/" + user["id"],
        json={"approved": True, "env_limit": 256, "role": "participant"},
    )
    assert alice.post("/api/runs", json=job).status_code == 422
    assert alice.post("/api/runs", json={**job, "num_envs": 256}).status_code == 201
    s["default_envs"] = 256
    s["max_iterations"] = 10
    admin.put("/api/admin/settings", json=s)
    assert alice.get("/api/runs").json()[0]["spec"]["iterations"] == 20


def test_snapshot_immutable_matches_execution_and_excludes_secrets(
    setup, job, tmp_path
):
    app, db, cfg, client = setup
    alice = client("alice@example.org")
    (cfg.base_repo / ".env").write_text(
        "SECRET=must-not-leak"
    )  # untracked secrets never included
    response = alice.post("/api/runs", json=job)
    assert response.status_code == 201, response.text
    run = response.json()
    root = cfg.data / "snapshots" / run["id"]
    manifest = verify(root, run["snapshot"])
    assert all(".env" not in p for p in manifest["files"])
    assert (root / "hub_config.json").stat().st_mode & 0o222 == 0
    extracted = tmp_path / "worker-source"
    extract_snapshot(zip_tree(root), extracted, run["snapshot"])
    out = tmp_path / "output"
    out.mkdir()
    result = subprocess.run(
        [sys.executable, "-B", str(extracted / "mock_train.py")],
        env={**os.environ, "HUB_RUN_OUTPUT": str(out), "HUB_MOCK_STEP_SECONDS": "0"},
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert (
        json.loads((out / "resolved.json").read_text())["configuration"]
        == manifest["configuration"]
    )
    assert verify(extracted, run["snapshot"]) == manifest
    source = extracted / "booster_mjlab/src/example.py"
    source.chmod(0o644)
    source.write_text("REWARD=999")
    with pytest.raises(ValueError, match="Source changed"):
        verify(extracted, run["snapshot"])
    # Base worktree changes cannot silently alter an existing snapshot.
    (cfg.base_repo / "src/example.py").write_text("REWARD=222")
    assert verify(root, run["snapshot"]) == manifest
    assert (
        alice.get("/api/code/" + run["id"] + "/file?path=../../secret").status_code
        == 400
    )


def test_18_participants_more_jobs_than_capacity(setup, job):
    app, db, cfg, client = setup
    admin = client("admin@example.org")
    worker, server = enroll(app, admin, max_jobs=2)
    heartbeat(worker, total=24576, free=24576)
    emails = [f"student{i}@example.org" for i in range(18)]
    for email in emails:
        admin.post("/api/admin/users", json={"email": email})
    clients = [client(email) for email in emails]
    with ThreadPoolExecutor(max_workers=9) as pool:
        responses = list(pool.map(lambda c: c.post("/api/runs", json=job), clients))
    assert all(r.status_code == 201 for r in responses)
    jobs = admin.get("/api/runs").json()
    assert sum(j["status"] == "STARTING" for j in jobs) == 2
    assert sum(j["status"] == "QUEUED" for j in jobs) == 16
    # Complete two waves; admission continues automatically on heartbeat.
    for _ in range(2):
        assignments = heartbeat(worker).json()["assignments"]
        for a in assignments:
            worker.post(
                "/api/worker/runs/" + a["id"] + "/claim", json={"lease": a["lease"]}
            )
            assert (
                worker.post(
                    "/api/worker/runs/" + a["id"] + "/report",
                    json={
                        "lease": a["lease"],
                        "status": "COMPLETED",
                        "iteration": 20,
                        "execution": {"mock": True},
                    },
                ).status_code
                == 200
            )
    heartbeat(worker)
    counts = admin.get("/api/admin/overview").json()["jobs"]
    assert (
        counts["COMPLETED"] == 4 and counts["STARTING"] == 2 and counts["QUEUED"] == 12
    )


def test_mps_fallback_limits_and_required_scheduling(setup, job):
    cfg = {
        "mps_enabled": True,
        "mps_kind": "legacy",
        "mps_required": False,
        "mps_pipe": "/tmp/workshop-mps",
        "mps_log": "/tmp/workshop-log",
        "mps_threads": 35,
        "mps_memory_mb": 8000,
    }
    env, enabled = mps_environment(cfg, {"mps": {"ready": False}}, "GPU-x")
    assert env == {} and not enabled
    with pytest.raises(RuntimeError):
        mps_environment(
            {**cfg, "mps_required": True}, {"mps": {"ready": False}}, "GPU-x"
        )
    env, enabled = mps_environment(cfg, {"mps": {"ready": True}}, "GPU-x")
    assert enabled and env["CUDA_MPS_ACTIVE_THREAD_PERCENTAGE"] == "35"
    assert env["CUDA_MPS_PINNED_DEVICE_MEM_LIMIT"] == "GPU-x=8000M"
    app, db, cfg_, client = setup
    admin = client("admin@example.org")
    alice = client("alice@example.org")
    worker, server = enroll(app, admin, mps_enabled=True, mps_required=True)
    heartbeat(worker, mps={"ready": False})
    key = alice.post("/api/runs", json=job).json()["id"]
    assert alice.get("/api/runs/" + key).json()["status"] == "QUEUED"
    heartbeat(worker, mps={"ready": True})
    assert alice.get("/api/runs/" + key).json()["status"] == "STARTING"


def test_worker_executes_frozen_mock_uploads_and_finishes(
    setup, job, tmp_path, monkeypatch
):
    from hub.worker import Worker

    app, db, cfg, client = setup
    admin = client("admin@example.org")
    alice = client("alice@example.org")
    _, server = enroll(app, admin, max_jobs=1)
    monkeypatch.setenv("HUB_MOCK_STEP_SECONDS", "0.001")
    agent = Worker(
        "http://127.0.0.1:8000", server["token"], tmp_path / "agent", mock=True
    )
    agent.client.close()
    agent.client = TestClient(app)
    agent.client.headers["Authorization"] = "Bearer " + server["token"]
    agent.heartbeat()
    response = alice.post("/api/runs", json=job)
    assert response.status_code == 201, response.text
    key = response.json()["id"]
    agent.heartbeat()
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        r = alice.get("/api/runs/" + key).json()
        if r["status"] in ("COMPLETED", "FAILED"):
            break
        time.sleep(0.05)
    agent.pool.shutdown(wait=True)
    agent.client.close()
    assert r["status"] == "COMPLETED", r.get("error")
    assert r["iteration"] == 20 and r["execution"]["mock"]
    assert r["execution"]["snapshot_sha256"] == r["snapshot"]
    assert any(a["path"] == "mock_checkpoint_20.json" for a in r["artifacts"])
    assert "HUB_METRIC" in alice.get("/api/runs/" + key + "/logs").json()["text"]
    assert verify(tmp_path / "agent" / key / "source", r["snapshot"])


def test_mps_v3_namespace_detection_and_client_environment(monkeypatch):
    from hub.hardware import mps_status

    cfg = {
        "mps_enabled": True,
        "mps_required": True,
        "mps_kind": "v3",
        "mps_pipe": "/run/site-mps",
        "mps_log": "/var/log/site-mps",
        "mps_server": "workshop",
        "mps_namespace": "students",
        "mps_threads": 30,
        "mps_memory_mb": 6000,
    }
    calls = []
    monkeypatch.setattr(
        "hub.hardware.shutil.which", lambda _: "/usr/bin/nvidia-cuda-mps-control"
    )

    def run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(
            args,
            0,
            "students,workshop,Ready,8G,50,0,/run/site-mps/workshop/students\n",
            "",
        )

    monkeypatch.setattr("hub.hardware.subprocess.run", run)
    status = mps_status(cfg)
    assert status["ready"] and calls[0][1:3] == ["namespace", "list"]
    env, enabled = mps_environment(cfg, {"mps": status}, "GPU-test")
    assert enabled and env["CUDA_MPS_PROTOCOL_VERSION"] == "3"
    assert env["CUDA_MPS_PIPE_DIRECTORY"] == "/run/site-mps/workshop/students"
    assert all("quit" not in arg and "delete" not in arg for arg in calls[0])


def test_slurm_discovery_filters_to_allocated_gpu(monkeypatch):
    from hub.hardware import discover

    monkeypatch.setenv("SLURM_JOB_ID", "123")
    monkeypatch.setenv("SLURM_JOB_GPUS", "1")
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")  # remapped within the allocation
    monkeypatch.setattr("hub.hardware.shutil.which", lambda _: None)

    def command(args):
        if "--query-gpu=index,uuid" in args:
            return "0, GPU-outside\n1, GPU-assigned"
        if any("query-gpu=uuid" in x for x in args):
            return "GPU-outside, Outside, 24576, 24000, 0, 570\nGPU-assigned, Assigned, 95830, 90000, 0, 580"
        return ""

    monkeypatch.setattr("hub.hardware.command", command)
    report = discover()
    assert [g["uuid"] for g in report["gpus"]] == ["GPU-assigned"]
    monkeypatch.delenv("SLURM_JOB_GPUS")
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES")
    assert discover()["gpus"] == []  # fail closed when allocation identity is unknown


def test_worker_cancels_own_process_and_releases_participant_slot(
    setup, job, tmp_path, monkeypatch
):
    from hub.worker import Worker

    app, db, cfg, client = setup
    admin, alice = client("admin@example.org"), client("alice@example.org")
    _, server = enroll(app, admin, max_jobs=1)
    monkeypatch.setenv("HUB_MOCK_STEP_SECONDS", "0.02")
    agent = Worker(
        "http://127.0.0.1:8000", server["token"], tmp_path / "cancel-agent", mock=True
    )
    agent.client.close()
    agent.client = TestClient(app)
    agent.client.headers["Authorization"] = "Bearer " + server["token"]
    agent.heartbeat()
    response = alice.post("/api/runs", json={**job, "iterations": 200})
    assert response.status_code == 201
    key = response.json()["id"]
    agent.heartbeat()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        run = alice.get("/api/runs/" + key).json()
        if run["status"] == "RUNNING":
            break
        time.sleep(0.02)
    assert run["status"] == "RUNNING"
    alice.post("/api/runs/" + key + "/cancel")
    assert alice.post("/api/runs", json=job).status_code == 409
    agent.heartbeat()
    while time.monotonic() < deadline:
        run = alice.get("/api/runs/" + key).json()
        if run["status"] in ("COMPLETED", "FAILED", "CANCELED"):
            break
        time.sleep(0.02)
    agent.pool.shutdown(wait=True)
    agent.client.close()
    assert run["status"] == "CANCELED", run.get("error")
    assert (
        json.loads((tmp_path / "cancel-agent" / key / "journal.json").read_text())[
            "state"
        ]
        == "finished"
    )
    assert alice.post("/api/runs", json=job).status_code == 201
