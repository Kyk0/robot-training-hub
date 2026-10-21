"""Paired training benchmark, using one immutable source snapshot.
Provision MPS separately; this script never starts/stops daemons or changes compute modes.
"""

import argparse
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import time
from hub.hardware import discover, mps_environment
from hub.snapshots import verify
from hub.scheduler import minimum_free_mb

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--source", type=Path, required=True)
p.add_argument("--training-python", required=True)
p.add_argument("--gpu", required=True)
p.add_argument("--concurrency", type=int, default=2)
p.add_argument("--mps-config", type=Path, required=True)
p.add_argument("--output", type=Path, required=True)
p.add_argument(
    "--motion-csv",
    type=Path,
    help="Original approved CSV, required for an uploaded CSV snapshot",
)
p.add_argument(
    "--estimated-job-mb",
    type=int,
    help="Override admission estimate using a measured per-job peak plus headroom",
)
p.add_argument(
    "--authorized",
    action="store_true",
    help="Confirm host owner permits these training runs inside any required allocation",
)
a = p.parse_args()
if not a.authorized:
    p.error("--authorized is required to run training on a shared host")
if not 1 <= a.concurrency <= 18:
    p.error("Concurrency must be 1–18")
source = a.source.resolve()
manifest = verify(source)
spec = manifest["configuration"]
if spec["motion"]["artifact"].startswith("upload:"):
    import hashlib

    if (
        not a.motion_csv
        or hashlib.sha256(a.motion_csv.read_bytes()).hexdigest()
        != spec["motion"]["sha256"]
    ):
        p.error("--motion-csv must match the approved snapshot CSV checksum")
cfg = json.loads(a.mps_config.read_text())
inv = discover(cfg)
if inv["institutional_scheduler"] and not inv.get("slurm_job_id"):
    p.error("Run inside an approved Slurm allocation")
if not inv["mps"]["ready"]:
    p.error("Existing MPS service is not ready")
a.output.mkdir(parents=True, exist_ok=False)
results = []
estimated = a.estimated_job_mb or int((4096 + 5 * spec["num_envs"]) * 1.3)
if estimated <= 0:
    p.error("Estimated memory must be positive")
for enabled in (False, True):
    inv = discover(cfg)
    selected = next((g for g in inv["gpus"] if g["uuid"] == a.gpu), None)
    if not selected:
        p.error("GPU is not visible inside this worker's allocation")
    required = estimated * a.concurrency + minimum_free_mb(
        selected,
        {
            "reserve_mb": cfg.get("reserve_mb", 46080),
            "margin_mb": cfg.get("margin_mb", 2048),
            "gpu_memory_percent": cfg.get("gpu_memory_percent", 80),
        },
    )
    if selected["free_mb"] < required:
        p.error(f"Insufficient free memory: need {required} MiB including reservations")
    env = {k: v for k, v in os.environ.items() if not k.startswith("CUDA_MPS_")}
    env.update(
        {
            "CUDA_VISIBLE_DEVICES": a.gpu,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
            "MUJOCO_GL": os.getenv("MUJOCO_GL", "disable"),
        }
    )
    if enabled:
        env.update(mps_environment({**cfg, "mps_required": True}, inv, a.gpu)[0])
    jobs = []
    logs = []
    start = time.monotonic()
    peak_mb = 0
    peak_used = 0
    returncodes = []
    try:
        for i in range(a.concurrency):
            out = a.output / ("mps" if enabled else "normal") / str(i)
            out.mkdir(parents=True)
            if a.motion_csv:
                (out / "motion").mkdir()
                shutil.copy2(a.motion_csv, out / "motion/input.csv")
            local = {**env, "HUB_RUN_OUTPUT": str(out.resolve())}
            f = (out / "training.log").open("w")
            logs.append(f)
            jobs.append(
                subprocess.Popen(
                    [a.training_python, "-B", str(source / "hub_launch.py")],
                    env=local,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    cwd=out,
                    start_new_session=True,
                )
            )
        while any(j.poll() is None for j in jobs):
            inventory = discover(cfg)
            gpu = next(g for g in inventory["gpus"] if g["uuid"] == a.gpu)
            used = gpu["total_mb"] - gpu["free_mb"]
            peak_used = max(peak_used, used)
            baseline = next(g for g in inv["gpus"] if g["uuid"] == a.gpu)
            peak_mb = max(peak_mb, used - (baseline["total_mb"] - baseline["free_mb"]))
            if gpu["free_mb"] < minimum_free_mb(
                gpu,
                {
                    "reserve_mb": cfg.get("reserve_mb", 46080),
                    "margin_mb": cfg.get("margin_mb", 2048),
                    "gpu_memory_percent": cfg.get("gpu_memory_percent", 80),
                },
            ):
                raise RuntimeError(
                    "Reservation crossed; stopping benchmark clients safely"
                )
            time.sleep(1)
        returncodes = [j.wait() for j in jobs]
    finally:
        for j in jobs:
            if j.poll() is None:
                os.killpg(j.pid, signal.SIGINT)
        for f in logs:
            f.close()
    elapsed = time.monotonic() - start
    from hub.worker import Worker

    reader = object.__new__(Worker)
    metrics = [
        reader.tensorboard(a.output / ("mps" if enabled else "normal") / str(i))[1]
        for i in range(a.concurrency)
    ]
    result = {
        "mps": enabled,
        "concurrency": a.concurrency,
        "wall_seconds": elapsed,
        "returncodes": returncodes,
        "aggregate_iterations_per_second": a.concurrency * spec["iterations"] / elapsed
        if all(c == 0 for c in returncodes)
        else None,
        "estimated_environment_steps_per_second": a.concurrency
        * spec["iterations"]
        * spec["num_envs"]
        * 24
        / elapsed
        if all(c == 0 for c in returncodes)
        else None,
        "peak_total_gpu_memory_mb": peak_used,
        "peak_incremental_memory_mb": peak_mb,
        "per_job_metrics": metrics,
        "snapshot": manifest["commits"],
    }
    results.append(result)
    (a.output / "results.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(result, indent=2))
verify(source)
