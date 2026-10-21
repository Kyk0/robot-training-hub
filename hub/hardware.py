"""Read-only discovery; MPS clients attach to an explicitly provisioned service."""

import csv
import io
import os
from pathlib import Path
import shutil
import subprocess


def command(args):
    try:
        return subprocess.check_output(
            args, text=True, stderr=subprocess.DEVNULL, timeout=8
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def discover(mps_cfg=None):
    data = command(
        [
            "nvidia-smi",
            "--query-gpu=uuid,name,memory.total,memory.free,utilization.gpu,driver_version",
            "--format=csv,noheader,nounits",
        ]
    )
    gpus = []
    for row in csv.reader(io.StringIO(data)):
        if len(row) == 6:
            uuid, name, total, free, util, driver = (x.strip() for x in row)
            gpus.append(
                dict(
                    uuid=uuid,
                    name=name,
                    total_mb=int(float(total)),
                    free_mb=int(float(free)),
                    utilization=int(float(util)),
                    driver=driver,
                )
            )
    if os.getenv("SLURM_JOB_ID"):
        # Slurm may expose all GPUs through nvidia-smi even inside a GPU allocation.
        # SLURM_*_GPUS are physical IDs; CUDA_VISIBLE_DEVICES may use remapped IDs.
        allocated = (
            os.getenv("SLURM_STEP_GPUS")
            or os.getenv("SLURM_JOB_GPUS")
            or os.getenv("CUDA_VISIBLE_DEVICES", "")
        )
        indexes = command(
            ["nvidia-smi", "--query-gpu=index,uuid", "--format=csv,noheader,nounits"]
        )
        by_index = {
            row[0].strip(): row[1].strip()
            for row in csv.reader(io.StringIO(indexes))
            if len(row) == 2
        }
        allowed = set()
        for token in allocated.split(","):
            token = token.strip()
            if token in by_index:
                allowed.add(by_index[token])
            elif token.startswith("GPU-"):
                matches = [g["uuid"] for g in gpus if g["uuid"].startswith(token)]
                if len(matches) == 1:
                    allowed.add(matches[0])
        if os.getenv("CUDA_VISIBLE_DEVICES") in ("", "-1", "NoDevFiles"):
            allowed.clear()
        gpus = [g for g in gpus if g["uuid"] in allowed]
    mps = mps_status(mps_cfg or {})
    return {
        "gpus": gpus,
        "mps": mps,
        "cuda": command(["nvcc", "--version"]),
        "institutional_scheduler": bool(
            shutil.which("srun") or Path("/etc/slurm/slurm.conf").exists()
        ),
        "slurm_job_id": os.getenv("SLURM_JOB_ID"),
        "hostname": command(["hostname"]),
    }


def mps_status(cfg):
    binary = shutil.which("nvidia-cuda-mps-control")
    pipe = cfg.get("mps_pipe", "")
    ready = False
    reason = "MPS disabled"
    client_pipe = pipe
    if cfg.get("mps_enabled"):
        reason = (
            "MPS control utility unavailable"
            if not binary
            else "Explicit MPS pipe and log directories required"
        )
        if binary and pipe and cfg.get("mps_log") and cfg.get("mps_kind") == "legacy":
            env = {
                **os.environ,
                "CUDA_MPS_PIPE_DIRECTORY": pipe,
                "CUDA_MPS_LOG_DIRECTORY": cfg["mps_log"],
            }
            try:
                p = subprocess.run(
                    [binary],
                    input="get_server_list\n",
                    capture_output=True,
                    text=True,
                    env=env,
                    timeout=5,
                )
                ready = (
                    p.returncode == 0 and "error" not in (p.stdout + p.stderr).lower()
                )
                reason = (
                    "Attached to existing service"
                    if ready
                    else "No accessible daemon in configured pipe"
                )
            except (OSError, subprocess.SubprocessError):
                reason = "MPS query failed"
        elif cfg.get("mps_kind") == "v3":
            reason = "MPS v3 requires an existing named server and namespace"
            if binary and pipe and cfg.get("mps_server") and cfg.get("mps_namespace"):
                env = {
                    **os.environ,
                    "CUDA_MPS_PIPE_DIRECTORY": pipe,
                    "CUDA_MPS_PROTOCOL_VERSION": "3",
                }
                try:
                    p = subprocess.run(
                        [
                            binary,
                            "namespace",
                            "list",
                            cfg["mps_namespace"],
                            "--server=" + cfg["mps_server"],
                            "--format=csv,noheader",
                        ],
                        capture_output=True,
                        text=True,
                        env=env,
                        timeout=5,
                    )
                    rows = list(csv.reader(io.StringIO(p.stdout)))
                    if p.returncode == 0 and rows and len(rows[0]) >= 7:
                        row = [x.strip() for x in rows[0]]
                        ready = (
                            row[0] == cfg["mps_namespace"]
                            and row[1] == cfg["mps_server"]
                            and row[2].lower() == "ready"
                            and row[6].startswith("/")
                        )
                        if ready:
                            client_pipe = row[6]
                    reason = (
                        "Attached to existing v3 namespace"
                        if ready
                        else "Configured v3 namespace is not ready"
                    )
                except (OSError, subprocess.SubprocessError):
                    reason = "MPS v3 query failed; legacy commands were not sent"
    return {
        "available": bool(binary),
        "ready": ready,
        "kind": cfg.get("mps_kind", "unknown"),
        "reason": reason,
        "pipe": pipe,
        "client_pipe": client_pipe,
    }


def mps_environment(cfg, inventory, gpu):
    if not cfg.get("mps_enabled"):
        return {}, False
    status = inventory.get("mps", {})
    if not status.get("ready"):
        if cfg.get("mps_required"):
            raise RuntimeError(
                "Required MPS service unavailable or unsupported generation"
            )
        return {}, False
    env = {
        "CUDA_MPS_PIPE_DIRECTORY": status.get("client_pipe") or cfg["mps_pipe"],
        "CUDA_MPS_LOG_DIRECTORY": cfg["mps_log"],
        "CUDA_MPS_ACTIVE_THREAD_PERCENTAGE": str(cfg["mps_threads"]),
    }
    if cfg.get("mps_memory_mb"):
        env["CUDA_MPS_PINNED_DEVICE_MEM_LIMIT"] = f"{gpu}={cfg['mps_memory_mb']}M"
    if cfg.get("mps_kind") == "v3":
        env["CUDA_MPS_PROTOCOL_VERSION"] = "3"
    return env, True
