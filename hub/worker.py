"""Outbound-only worker. No shell/RCE API. One authenticated coordinator per service."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import logging
import os
from pathlib import Path
import queue
import re
import signal
import subprocess
import sys
import threading
import time
import httpx
from .db import pack, uid
from .hardware import discover, mps_environment, command
from .snapshots import extract_snapshot, verify, sha

log = logging.getLogger("worker")


class Worker:
    def __init__(
        self,
        url,
        token,
        root,
        training_python=None,
        mock=False,
        mock_memory=24576,
        name="mock",
    ):
        if not url.startswith("https://") and not (
            url.startswith("http://127.0.0.1:") or url.startswith("http://localhost:")
        ):
            raise ValueError("Worker coordinator must use HTTPS outside loopback")
        self.client = httpx.Client(
            base_url=url, headers={"Authorization": "Bearer " + token}, timeout=30
        )
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.training_python = training_python or sys.executable
        self.mock = mock
        self.mock_memory = mock_memory
        self.name = name
        self.boot = uid()
        self.config = {}
        self.active = {}
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.unresolved = []
        for f in self.root.glob("*/journal.json"):
            try:
                state = json.loads(f.read_text())
                if state.get("state") != "finished":
                    self.unresolved.append(f.parent.name)
            except (ValueError, OSError):
                self.unresolved.append(f.parent.name)
        self.pool = ThreadPoolExecutor(max_workers=18)

    def inventory(self):
        if not self.mock:
            return discover(self.config)
        with self.lock:
            used = sum(v.get("memory", 0) for v in self.active.values())
        return {
            "gpus": [
                {
                    "uuid": "MOCK-" + self.name,
                    "name": "SIMULATED GPU — " + self.name,
                    "total_mb": self.mock_memory,
                    "free_mb": max(0, self.mock_memory - used),
                    "utilization": min(100, len(self.active) * 35),
                    "driver": "MOCK",
                }
            ],
            "mps": {
                "ready": False,
                "available": False,
                "reason": "Mock worker — no CUDA",
            },
            "cuda": "mock",
            "institutional_scheduler": False,
            "slurm_job_id": None,
            "hostname": self.name,
            "mock": True,
        }

    def post(self, path, body):
        r = self.client.post(path, json=body)
        r.raise_for_status()
        return r.json()

    def heartbeat(self):
        with self.lock:
            ids = list(self.active)
        response = self.post(
            "/api/worker/heartbeat",
            {
                "boot_id": self.boot,
                "inventory": self.inventory(),
                "active": ids,
                "unresolved": self.unresolved,
            },
        )
        self.config = response["config"]
        for assignment in response["assignments"]:
            key = assignment["id"]
            with self.lock:
                state = self.active.get(key)
                if state:
                    if assignment["cancel"]:
                        state["cancel"].set()
                    continue
                if (
                    response["quarantined"]
                    or key in self.unresolved
                    or assignment["acknowledged"]
                ):
                    continue
                self.active[key] = {
                    "cancel": threading.Event(),
                    "memory": 0,
                    "process": None,
                }
            self.pool.submit(self.execute, assignment)

    def journal(self, directory, data):
        temp = directory / "journal.tmp"
        temp.write_text(pack(data))
        temp.replace(directory / "journal.json")

    def report_retry(self, key, body):
        while not self.stop.is_set():
            try:
                return self.post(f"/api/worker/runs/{key}/report", body)
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (401, 403, 404, 409, 422):
                    raise
                log.warning(
                    "Coordinator rejected report temporarily: %s",
                    e.response.status_code,
                )
            except httpx.HTTPError:
                log.warning("Coordinator disconnected; run retained, report pending")
            self.stop.wait(3)
        raise RuntimeError("Worker stopping; journal retained for reconciliation")

    def upload_retry(self, key, lease, path, name):
        while not self.stop.is_set():
            try:
                with path.open("rb") as content:
                    r = self.client.put(
                        f"/api/worker/runs/{key}/artifact",
                        params={"path": name},
                        headers={
                            "X-Job-Lease": lease,
                            "Content-Type": "application/octet-stream",
                        },
                        content=content,
                    )
                r.raise_for_status()
                return
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (401, 403, 404, 409, 413, 422):
                    raise
            except httpx.HTTPError:
                pass
            self.stop.wait(3)
        raise RuntimeError("Upload pending at shutdown")

    def memory(self, pid):
        if self.mock:
            return 0
        data = command(
            [
                "nvidia-smi",
                "--query-compute-apps=pid,used_memory",
                "--format=csv,noheader,nounits",
            ]
        )
        total = 0
        for row in data.splitlines():
            cells = [x.strip() for x in row.split(",")]
            if len(cells) == 2 and cells[0] == str(pid):
                try:
                    total += int(cells[1])
                except ValueError:
                    pass
        # Legacy MPS attributes memory to the daemon; scheduler retains full estimates instead.
        return total

    def tensorboard(self, output):
        metrics = {}
        step = 0
        try:
            from tensorboard.backend.event_processing.event_accumulator import (
                EventAccumulator,
            )

            for event in sorted(output.rglob("events.out.tfevents*"))[-3:]:
                acc = EventAccumulator(str(event), size_guidance={"scalars": 1})
                acc.Reload()
                for tag in acc.Tags().get("scalars", []):
                    vals = acc.Scalars(tag)
                    if vals:
                        v = vals[-1]
                        step = max(step, v.step + 1)
                        if "reward" in tag.lower() and "mean" in tag.lower():
                            metrics["reward"] = v.value
                        elif "iteration" in tag.lower() and "time" in tag.lower():
                            metrics["iteration_seconds"] = v.value
                        elif "fps" in tag.lower():
                            metrics["fps"] = v.value
        except Exception:
            log.debug("Tensorboard not yet readable", exc_info=True)
        return step, metrics

    def execute(self, assignment):
        key = assignment["id"]
        lease = assignment["lease"]
        state = self.active[key]
        directory = self.root / key
        directory.mkdir(exist_ok=True)
        output = directory / "output"
        output.mkdir(exist_ok=True)
        proc = None
        execution = None
        iteration = 0
        logseq = 0
        finished = False
        claimed = False
        try:
            self.journal(
                directory, {"state": "claiming", "lease": lease, "boot": self.boot}
            )
            claim = self.post(f"/api/worker/runs/{key}/claim", {"lease": lease})
            claimed = True
            if claim["cancel"]:
                state["cancel"].set()
            if state["cancel"].is_set():
                self.report_retry(key, {"lease": lease, "status": "CANCELED"})
                finished = True
                return
            response = self.client.get(f"/api/worker/runs/{key}/source")
            response.raise_for_status()
            source = directory / "source"
            extract_snapshot(response.content, source, assignment["snapshot"])
            cfg = assignment["config"]
            inv = self.inventory()
            if not self.mock:
                if inv["institutional_scheduler"] and not os.getenv("SLURM_JOB_ID"):
                    raise RuntimeError(
                        "Institutional scheduler detected: run worker inside approved Slurm allocation"
                    )
                if not cfg["institutional_permission"]:
                    raise RuntimeError("Host not authorized for direct training")
                gpu = next(
                    (g for g in inv["gpus"] if g["uuid"] == assignment["gpu"]), None
                )
                if (
                    not gpu
                    or gpu["free_mb"] - cfg["reserve_mb"] - cfg["margin_mb"]
                    < assignment["estimated_mb"]
                ):
                    raise RuntimeError(
                        "GPU capacity changed before launch; reservation would be violated"
                    )
                if not Path(self.training_python).is_file():
                    raise RuntimeError(
                        "Existing mjlab training interpreter is unavailable"
                    )
            # No inherited MPS settings: normal jobs must not attach to an existing daemon accidentally.
            env = {
                k: v
                for k, v in os.environ.items()
                if not k.startswith(
                    ("CUDA_MPS_", "HUB_WORKER_TOKEN", "HUB_SMTP_", "HUB_TOKEN")
                )
            }
            env.update(
                {
                    "CUDA_VISIBLE_DEVICES": assignment["gpu"],
                    "HUB_RUN_OUTPUT": str(output),
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONUNBUFFERED": "1",
                    "MUJOCO_GL": os.getenv("MUJOCO_GL", "disable"),
                    "PYTHONPATH": os.pathsep.join(
                        [str(source / "booster_mjlab/src"), str(source / "mjlab/src")]
                    ),
                }
            )
            mps_env, mps = (
                mps_environment(cfg, inv, assignment["gpu"])
                if not self.mock
                else ({}, False)
            )
            env.update(mps_env)
            entry = "mock_train.py" if self.mock else "hub_launch.py"
            args = [self.training_python, "-B", str(source / entry)]
            execution = {
                "argv": args,
                "cwd": str(output),
                "source": str(source),
                "snapshot_sha256": assignment["snapshot"],
                "mps": mps,
                "mps_kind": cfg.get("mps_kind"),
                "mps_environment": mps_env,
                "mock": self.mock,
                "training_python": self.training_python,
            }
            (output / "execution.json").write_text(pack(execution))
            verify(source, assignment["snapshot"])
            if state["cancel"].is_set():
                self.report_retry(
                    key, {"lease": lease, "status": "CANCELED", "execution": execution}
                )
                finished = True
                return
            with (directory / "training.log").open("a") as local:
                proc = subprocess.Popen(
                    args,
                    cwd=output,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    start_new_session=True,
                )
                state["process"] = proc
                state["memory"] = assignment["estimated_mb"]
                self.journal(
                    directory,
                    {
                        "state": "running",
                        "pid": proc.pid,
                        "lease": lease,
                        "boot": self.boot,
                        "execution": execution,
                    },
                )
                lines = queue.Queue()

                def reader():
                    for line in proc.stdout:
                        lines.put(line)
                    lines.put(None)

                thread = threading.Thread(target=reader, daemon=True)
                thread.start()
                metrics = {}
                pending = ""
                last = 0
                cancel_at = None
                reader_done = False
                resource_error = None
                while proc.poll() is None or not reader_done:
                    if self.stop.is_set():
                        state["cancel"].set()
                    if state["cancel"].is_set() and cancel_at is None:
                        os.killpg(proc.pid, signal.SIGINT)
                        cancel_at = time.monotonic()
                    if (
                        cancel_at
                        and proc.poll() is None
                        and time.monotonic() - cancel_at > 30
                    ):
                        # Never SIGKILL an active MPS client: leave capacity quarantined for site-safe termination.
                        if mps:
                            raise RuntimeError(
                                "MPS client did not exit after SIGINT; administrator must terminate this client through MPS before reconciliation"
                            )
                        os.killpg(proc.pid, signal.SIGTERM)
                        if time.monotonic() - cancel_at > 40:
                            os.killpg(proc.pid, signal.SIGKILL)
                    try:
                        line = lines.get(timeout=0.2)
                        if line is None:
                            reader_done = True
                        else:
                            # Avoid publishing common credential values should a library print them.
                            for name in ("WANDB_API_KEY", "HF_TOKEN"):
                                if os.getenv(name):
                                    line = line.replace(os.environ[name], "[REDACTED]")
                            local.write(line)
                            local.flush()
                            pending += line
                            if line.startswith("HUB_METRIC "):
                                value = json.loads(line[11:])
                                iteration = value.pop("iteration")
                                metrics.update(value)
                            else:
                                match = re.search(
                                    r"Learning iteration\s+(\d+)\s*/", line, re.I
                                )
                                if match:
                                    iteration = int(match[1]) + 1
                    except queue.Empty:
                        pass
                    if time.monotonic() - last > 2 or len(pending) > 64000:
                        if not self.mock:
                            live_gpu = next(
                                (
                                    g
                                    for g in self.inventory()["gpus"]
                                    if g["uuid"] == assignment["gpu"]
                                ),
                                None,
                            )
                            if (
                                live_gpu
                                and live_gpu["free_mb"]
                                < cfg["reserve_mb"] + cfg["margin_mb"]
                            ):
                                resource_error = "GPU free memory fell below the configured reservation; this workshop job was stopped"
                                state["cancel"].set()
                            step, values = self.tensorboard(output)
                            iteration = max(iteration, step)
                            metrics.update(values)
                        body = {
                            "lease": lease,
                            "iteration": min(
                                iteration, assignment["spec"]["iterations"]
                            ),
                            "metrics": metrics,
                            "logs": pending[:120000],
                            "log_seq": logseq,
                            "gpu_mb": self.memory(proc.pid),
                            "execution": execution,
                        }
                        result = self.report_retry(key, body)
                        if result.get("terminal"):
                            raise RuntimeError(
                                "Coordinator finalized a process that is still active"
                            )
                        if result.get("cancel"):
                            state["cancel"].set()
                        pending = pending[120000:]
                        logseq += 1
                        last = time.monotonic()
                proc.wait()
                if pending:
                    self.report_retry(
                        key,
                        {
                            "lease": lease,
                            "iteration": iteration,
                            "metrics": metrics,
                            "logs": pending[:120000],
                            "log_seq": logseq,
                            "execution": execution,
                        },
                    )
            verify(source, assignment["snapshot"])
            artifacts = []
            for pattern in ("*.yaml", "*.yml", "*.json"):
                artifacts.extend(
                    p
                    for p in output.rglob(pattern)
                    if "motion" not in p.relative_to(output).parts
                )
            checkpoints = sorted(output.rglob("*.pt"), key=lambda p: p.stat().st_mtime)[
                -3:
            ]
            for path in artifacts + checkpoints:
                self.upload_retry(key, lease, path, str(path.relative_to(output)))
            status = (
                "FAILED"
                if resource_error
                else "CANCELED"
                if state["cancel"].is_set()
                else "COMPLETED"
                if proc.returncode == 0
                else "FAILED"
            )
            error = resource_error or (
                None
                if proc.returncode == 0 or status == "CANCELED"
                else f"Training exited with code {proc.returncode}; inspect logs"
            )
            self.report_retry(
                key,
                {
                    "lease": lease,
                    "status": status,
                    "iteration": min(iteration, assignment["spec"]["iterations"]),
                    "metrics": metrics,
                    "execution": execution,
                    "error": error,
                },
            )
            finished = True
        except Exception as e:
            log.exception("Run %s failed", key)
            alive = proc is not None and proc.poll() is None
            if alive:
                self.unresolved.append(key)
                # Retain RUNNING allocation: no false failure/retry while a client may still run.
            elif claimed:
                try:
                    self.report_retry(
                        key,
                        {
                            "lease": lease,
                            "status": "FAILED",
                            "iteration": min(
                                iteration, assignment["spec"]["iterations"]
                            ),
                            "execution": execution,
                            "error": str(e)[:4000],
                        },
                    )
                    finished = True
                except Exception:
                    log.exception("Failure report remains unresolved")
            else:
                self.unresolved.append(key)
        finally:
            if finished:
                self.journal(directory, {"state": "finished", "lease": lease})
            with self.lock:
                self.active.pop(key, None)

    def run(self):
        try:
            while not self.stop.is_set():
                try:
                    self.heartbeat()
                except Exception:
                    log.exception("Heartbeat failed; existing jobs remain owned")
                self.stop.wait(3)
        finally:
            self.stop.set()
            self.pool.shutdown(wait=True)
            self.client.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--coordinator", default=os.getenv("HUB_COORDINATOR", "http://127.0.0.1:8000")
    )
    p.add_argument("--root", default=os.getenv("HUB_WORKER_ROOT", "worker-runs"))
    p.add_argument("--token-file", default=os.getenv("HUB_WORKER_TOKEN_FILE"))
    p.add_argument("--training-python", default=os.getenv("HUB_TRAINING_PYTHON"))
    p.add_argument("--mock", action="store_true")
    p.add_argument("--mock-memory", type=int, default=24576)
    p.add_argument("--name", default="mock")
    args = p.parse_args()
    token = (
        Path(args.token_file).read_text().strip()
        if args.token_file
        else os.getenv("HUB_WORKER_TOKEN")
    )
    if not token:
        p.error("Set --token-file or HUB_WORKER_TOKEN")
    if not args.mock and not args.training_python:
        p.error(
            "Real workers require --training-python pointing at the existing Booster mjlab .venv/bin/python"
        )
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    worker = Worker(
        args.coordinator,
        token,
        args.root,
        args.training_python,
        args.mock,
        args.mock_memory,
        args.name,
    )
    signal.signal(signal.SIGTERM, lambda *_: worker.stop.set())
    signal.signal(signal.SIGINT, lambda *_: worker.stop.set())
    worker.run()


if __name__ == "__main__":
    main()
