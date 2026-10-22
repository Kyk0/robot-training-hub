import os
from hub.worker import publication_artifacts


def test_worker_publishes_onnx_and_recent_checkpoints(tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    policy = output / "training" / "run" / "run.onnx"
    policy.parent.mkdir(parents=True)
    policy.write_bytes(b"unit-test-policy-artifact")
    config = policy.parent / "env.yaml"
    config.write_text("seed: 42\n")
    checkpoints = []
    for i in range(5):
        path = policy.parent / f"model_{i}.pt"
        path.write_bytes(b"checkpoint")
        os.utime(path, (100 + i, 100 + i))
        checkpoints.append(path)
    motion = output / "motion"
    motion.mkdir()
    (motion / "private.json").write_text("{}")
    manifest = motion / "manifest.json"
    manifest.write_text("{}")
    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    (output / "unsafe.json").symlink_to(outside)
    selected = publication_artifacts(output)
    assert policy in selected and config in selected and manifest in selected
    assert set(p for p in selected if p.suffix == ".pt") == set(checkpoints[-3:])
    assert (
        motion / "private.json" not in selected
        and output / "unsafe.json" not in selected
    )


def test_frozen_runner_versions_native_exports_and_keeps_latest_ten(
    tmp_path, monkeypatch
):
    import hashlib, json
    from hub.policy_export import versioned_runner

    monkeypatch.setattr("hub.policy_export.validate_onnx", lambda path: None)

    class NativeRunner:
        def save(self, path, infos=None):
            from pathlib import Path

            Path(path).write_bytes(b"unit-test-checkpoint")
            (tmp_path / "native.onnx").write_bytes(("export-" + str(path)).encode())

        def _get_export_paths(self, path):
            return tmp_path, "native.onnx", tmp_path / "native.onnx"

    spec = {
        "iterations": 1000,
        "run_id": "run",
        "task": "tracking",
        "motion": {"id": "dance"},
        "policy_interval": 50,
    }
    runner = versioned_runner(NativeRunner, tmp_path, spec)()
    for index in range(0, 601, 50):
        runner.save(str(tmp_path / f"model_{index}.pt"))
    files = sorted((tmp_path / "policies").glob("*.onnx"))
    assert len(files) == 10 and files[0].name.startswith("iteration_000150-")
    metadata = json.loads(files[-1].with_suffix(".json").read_text())
    assert metadata["iteration_index"] == 600 and metadata["policy_interval"] == 50
    assert metadata["sha256"] == hashlib.sha256(files[-1].read_bytes()).hexdigest()
    assert sorted(p.name for p in tmp_path.glob("model_*.pt")) == [
        "model_500.pt",
        "model_550.pt",
        "model_600.pt",
    ]


def test_checkpoint_retention_stays_inside_current_run(tmp_path):
    from hub.policy_export import retain_checkpoints

    output = tmp_path / "run"
    output.mkdir()
    for index in (0, 50, 100, 150):
        (output / f"model_{index}.pt").write_bytes(b"checkpoint")
    outside = tmp_path / "model_200.pt"
    outside.write_bytes(b"other run checkpoint")
    link = output / "model_200.pt"
    link.symlink_to(outside)
    named = output / "model_backup.pt"
    named.write_bytes(b"manual backup")
    retain_checkpoints(output, outside)
    assert (output / "model_0.pt").exists()
    retain_checkpoints(output, output / "model_150.pt")
    assert not (output / "model_0.pt").exists()
    assert all((output / f"model_{i}.pt").exists() for i in (50, 100, 150))
    assert outside.read_bytes() == b"other run checkpoint"
    assert named.read_bytes() == b"manual backup" and link.is_symlink()


def test_failed_native_save_preserves_previous_checkpoints(tmp_path):
    import pytest
    from hub.policy_export import versioned_runner

    class FailingRunner:
        def save(self, path, infos=None):
            raise OSError("disk write failed")

    for index in (0, 50, 100, 150):
        (tmp_path / f"model_{index}.pt").write_bytes(b"previous checkpoint")
    runner = versioned_runner(FailingRunner, tmp_path, {})()
    with pytest.raises(OSError, match="disk write failed"):
        runner.save(str(tmp_path / "model_200.pt"))
    assert len(list(tmp_path.glob("model_*.pt"))) == 4


def test_policy_catalog_export_ownership_and_terminal_publication(setup, job):
    import io, json, zipfile
    from conftest import enroll, heartbeat

    app, db, cfg, client = setup
    admin, alice, bob = (
        client("admin@example.org"),
        client("alice@example.org"),
        client("bob@example.org"),
    )
    worker, _ = enroll(app, admin)
    heartbeat(worker)
    run = alice.post("/api/runs", json=job).json()
    key = run["id"]
    assigned = heartbeat(worker).json()["assignments"][0]
    lease = assigned["lease"]
    worker.post(
        "/api/worker/runs/" + key + "/claim", json={"lease": lease}
    ).raise_for_status()
    headers = {"X-Job-Lease": lease}
    worker.put(
        "/api/worker/runs/" + key + "/artifact",
        params={"path": "training/params/env.yaml"},
        headers=headers,
        content=b"seed: 42\n",
    ).raise_for_status()
    worker.put(
        "/api/worker/runs/" + key + "/artifact",
        params={"path": "training/model_550.pt"},
        headers=headers,
        content=b"unit-test-checkpoint",
    ).raise_for_status()
    worker.post(
        "/api/worker/runs/" + key + "/report",
        json={
            "lease": lease,
            "status": "COMPLETED",
            "iteration": 20,
            "execution": {"mock": True},
        },
    ).raise_for_status()
    for index in range(0, 600, 50):
        path = f"policies/iteration_{index:06d}-0123456789ab.onnx"
        worker.put(
            "/api/worker/runs/" + key + "/artifact",
            params={"path": path},
            headers=headers,
            content=b"unit-test-policy",
        ).raise_for_status()
    rows = alice.get("/api/policies").json()
    assert len(rows) == 10 and len(admin.get("/api/policies").json()) == 10
    assert (
        next(row for row in rows if row["iteration_index"] == 550)["checkpoint_path"]
        == "training/model_550.pt"
    )
    assert (
        next(row for row in rows if row["iteration_index"] == 500)["checkpoint_path"]
        is None
    )
    assert bob.get("/api/policies").json() == []
    path = rows[0]["path"]
    url = "/api/runs/" + key + "/policies/export"
    assert bob.get(url, params={"path": path}).status_code == 404
    result = alice.get(url, params={"path": path})
    result.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(result.content)) as z:
        assert z.read("policy.onnx") == b"unit-test-policy"
        assert json.loads(z.read("manifest.json"))["run_id"] == key
        assert json.loads(z.read("manifest.json"))["training_commits"]
        assert z.read("config/training/params/env.yaml") == b"seed: 42\n"
    assert (
        worker.put(
            "/api/worker/runs/" + key + "/artifact",
            params={"path": path},
            headers=headers,
            content=b"changed",
        ).status_code
        == 409
    )
    assert (
        worker.put(
            "/api/worker/runs/" + key + "/artifact",
            params={"path": "model_50.pt"},
            headers=headers,
            content=b"late-checkpoint",
        ).status_code
        == 409
    )
    assert (
        worker.put(
            "/api/worker/runs/" + key + "/artifact",
            params={"path": path},
            headers={"X-Job-Lease": "wrong"},
            content=b"unit-test-policy",
        ).status_code
        == 404
    )
    assert (
        alice.get(
            "/api/runs/" + key + "/artifacts",
            params={"path": "policies/iteration_000000-0123456789ab.onnx"},
        ).status_code
        == 404
    )
