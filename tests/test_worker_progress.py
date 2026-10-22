import json
import threading
from types import SimpleNamespace

import pytest

from conftest import enroll, heartbeat
from hub.worker import Worker


def test_tensorboard_time_axis_is_not_training_progress(tmp_path):
    from tensorboard.summary.writer.event_file_writer import EventFileWriter
    from tensorboard.compat.proto.event_pb2 import Event
    from tensorboard.compat.proto.summary_pb2 import Summary

    writer = EventFileWriter(str(tmp_path / "events"))
    for tag, step, value in (
        ("Train/mean_reward", 10, 2.5),
        ("Train/mean_reward/time", 9000, 2.5),
        ("Perf/iteration_time", 10, 1.5),
        ("Perf/total_fps", 10, 1234),
    ):
        writer.add_event(
            Event(
                step=step,
                summary=Summary(value=[Summary.Value(tag=tag, simple_value=value)]),
            )
        )
    writer.close()
    agent = Worker("http://127.0.0.1:8000", "test", tmp_path / "worker", mock=True)
    try:
        step, metrics = agent.tensorboard(tmp_path / "events")
        assert step == 11
        assert metrics == {"reward": 2.5, "iteration_seconds": 1.5, "fps": 1234}
    finally:
        agent.pool.shutdown(wait=True)
        agent.client.close()


@pytest.mark.parametrize("cancel", [False, True])
def test_worker_handles_final_progress_and_already_exited_cancellation(
    setup, job, tmp_path, monkeypatch, cancel
):
    app, _, _, client = setup
    admin, alice = client("admin@example.org"), client("alice@example.org")
    worker, server = enroll(app, admin)
    heartbeat(worker)
    run = alice.post("/api/runs", json=job).json()
    assignment = heartbeat(worker).json()["assignments"][0]
    key = run["id"]
    agent = Worker(
        "http://127.0.0.1:8000", server["token"], tmp_path / "worker", mock=True
    )
    agent.client.close()
    agent.client = worker
    agent.active[key] = {"cancel": threading.Event(), "process": None, "memory": 0}
    original_post = agent.post

    def post(path, body):
        response = original_post(path, body)
        if cancel and path.endswith("/claim"):
            assert alice.post(f"/api/runs/{key}/cancel").status_code == 200
        return response

    agent.post = post
    fake = SimpleNamespace(
        pid=99999999,
        returncode=0,
        poll=lambda: 0,
        wait=lambda: 0,
        stdout=iter(
            [
                'HUB_METRIC {"iteration": 1}\n',
                'HUB_METRIC {"iteration": 9001}\n',
            ]
        ),
    )
    monkeypatch.setattr("hub.worker.subprocess.Popen", lambda *a, **kw: fake)
    signals = []

    def gone(pid, sig):
        signals.append((pid, sig))
        raise ProcessLookupError("Process already exited")

    monkeypatch.setattr("hub.worker.os.killpg", gone)
    try:
        agent.execute(assignment)
    finally:
        agent.pool.shutdown(wait=True)
        agent.client.close()
    result = alice.get(f"/api/runs/{key}").json()
    assert result["status"] == ("CANCELED" if cancel else "COMPLETED"), result.get(
        "error"
    )
    assert result["iteration"] == job["iterations"]
    assert not signals
    assert (
        json.loads((tmp_path / "worker" / key / "journal.json").read_text())["state"]
        == "finished"
    )
