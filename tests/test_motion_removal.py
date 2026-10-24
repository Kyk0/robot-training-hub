import hashlib
import importlib

import pytest
from fastapi.testclient import TestClient

from conftest import enroll, heartbeat
from hub.db import DB
from hub.snapshots import verify
from test_real_workflow import csv_bytes


def upload(client):
    r = client.post(
        "/api/motions?label=Workshop%20motion&shared=true", content=csv_bytes()
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_only_admin_can_remove_motion_and_removal_is_idempotent(setup, job):
    app, db, cfg, client = setup
    admin, alice, bob = (
        client(email)
        for email in ("admin@example.org", "alice@example.org", "bob@example.org")
    )
    motion = upload(alice)
    key = motion["id"]
    url = f"/api/admin/motions/{key}"
    assert (
        TestClient(app).delete(url, headers={"X-Hub-Request": "1"}).status_code == 401
    )
    assert alice.delete(url).status_code == 403
    assert bob.delete(url).status_code == 403
    assert admin.delete("/api/admin/motions/missing").status_code == 404
    assert (
        admin.post(
            url + "/approve", json={"approved": True, "shared": True}
        ).status_code
        == 200
    )
    for account in (admin, alice, bob):
        assert key in {m["id"] for m in account.get("/api/options").json()["motions"]}
    assert admin.delete(url).status_code == 200
    assert admin.delete(url).status_code == 200
    for account in (admin, alice, bob):
        assert key not in {m["id"] for m in account.get("/api/motions").json()}
        assert key not in {
            m["id"] for m in account.get("/api/options").json()["motions"]
        }
        assert account.get(f"/api/motions/{key}/preview").status_code == 404
        assert account.get(f"/api/motions/{key}/download").status_code == 404
        assert (
            account.post("/api/runs", json={**job, "motion_id": key}).status_code == 422
        )
    assert admin.post(url + "/approve", json={"approved": True}).status_code == 404
    with db.connect() as c:
        row = c.execute("SELECT * FROM motions WHERE id=?", (key,)).fetchone()
        assert row["deleted_at"] and not row["approved"] and not row["shared"]
        assert (
            c.execute(
                "SELECT count(*) FROM audit WHERE action='remove-motion'"
            ).fetchone()[0]
            == 1
        )
    assert (cfg.data / "motions" / key / "input.csv").read_bytes() == csv_bytes()


@pytest.mark.parametrize("running", [False, True])
def test_removed_motion_remains_available_to_existing_queued_and_running_jobs(
    setup, job, running
):
    app, db, cfg, client = setup
    admin, alice = client("admin@example.org"), client("alice@example.org")
    motion = upload(admin)
    if running:
        worker, _ = enroll(app, admin)
        heartbeat(worker)
    run = alice.post("/api/runs", json={**job, "motion_id": motion["id"]}).json()
    key = run["id"]
    if running:
        assignment = heartbeat(worker).json()["assignments"][0]
        assert (
            worker.post(
                f"/api/worker/runs/{key}/claim", json={"lease": assignment["lease"]}
            ).status_code
            == 200
        )
        assert (
            worker.post(
                f"/api/worker/runs/{key}/report",
                json={
                    "lease": assignment["lease"],
                    "status": "RUNNING",
                    "iteration": 1,
                },
            ).status_code
            == 200
        )
    before = alice.get(f"/api/runs/{key}").json()
    assert admin.delete(f"/api/admin/motions/{motion['id']}").status_code == 200
    after = alice.get(f"/api/runs/{key}").json()
    assert after["status"] == before["status"] == ("RUNNING" if running else "QUEUED")
    assert after["snapshot"] == before["snapshot"]
    assert after["spec"]["motion"] == before["spec"]["motion"]
    assert verify(cfg.data / "snapshots" / key, run["snapshot"])
    if not running:
        worker, _ = enroll(app, admin)
        assignment = heartbeat(worker).json()["assignments"][0]
    raw = worker.get(f"/api/worker/runs/{key}/motion")
    assert raw.status_code == 200
    assert hashlib.sha256(raw.content).hexdigest() == run["spec"]["motion"]["sha256"]
    assert worker.get(f"/api/worker/runs/{key}/source").status_code == 200


def test_motion_removal_during_snapshot_preparation_prevents_admission(
    setup, job, monkeypatch
):
    _, db, _, client = setup
    admin, alice = client("admin@example.org"), client("alice@example.org")
    motion = upload(admin)
    module = importlib.import_module("hub.app")
    original = module.create_snapshot

    def prepare_then_remove(*args, **kwargs):
        result = original(*args, **kwargs)
        assert admin.delete(f"/api/admin/motions/{motion['id']}").status_code == 200
        return result

    monkeypatch.setattr(module, "create_snapshot", prepare_then_remove)
    response = alice.post("/api/runs", json={**job, "motion_id": motion["id"]})
    assert response.status_code == 409, response.text
    assert "no longer available" in response.json()["detail"]
    with db.connect() as c:
        assert c.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0


def test_existing_database_gets_motion_removal_column_without_losing_uploads(setup):
    _, db, cfg, client = setup
    motion = upload(client("admin@example.org"))
    with db.connect() as c:
        c.execute("ALTER TABLE motions DROP COLUMN deleted_at")
    DB(cfg)
    DB(cfg)  # Idempotent restart migration.
    with db.connect() as c:
        row = c.execute("SELECT * FROM motions WHERE id=?", (motion["id"],)).fetchone()
        assert row["deleted_at"] is None and row["sha256"] == motion["sha256"]
