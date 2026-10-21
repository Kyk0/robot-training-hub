"""Durable admission. Unknown/disconnected runs retain capacity and never auto-retry."""

import math
from .db import ACTIVE, now, pack, uid, unpack


def estimate(settings, spec):
    p = settings["memory_profiles"]
    return math.ceil(
        (p["base_mb"] + p["per_env_mb"] * spec["num_envs"]) * p["safety_factor"]
    )


def minimum_free_mb(gpu, limits):
    return max(
        limits["reserve_mb"] + limits["margin_mb"],
        math.ceil(gpu["total_mb"] * (100 - limits.get("gpu_memory_percent", 80)) / 100),
    )


def headroom_mb(gpu, limits, current):
    # NVIDIA reports all users' processes. Count external usage and reserve
    # unmaterialized workshop allocations, including STARTING/disconnected jobs.
    measured = sum(j["gpu_mb"] for j in current)
    external = max(0, gpu["total_mb"] - gpu["free_mb"] - measured)
    committed = sum(max(j["estimated_mb"], j["gpu_mb"]) for j in current)
    return gpu["total_mb"] - minimum_free_mb(gpu, limits) - external - committed


def server_capacity(c, server, settings, online):
    cfg = unpack(server["config"])
    inv = unpack(server["inventory"])
    expected = estimate(settings, {"num_envs": settings["default_envs"]})
    running = c.execute(
        "SELECT count(*) FROM jobs WHERE status IN ('STARTING','RUNNING')"
    ).fetchone()[0]
    remaining = max(0, settings["max_running_jobs"] - running)
    result = []
    for gpu in inv.get("gpus", []):
        limits = {
            **cfg,
            **cfg.get("gpu_limits", {}).get(gpu["uuid"], {}),
            "gpu_memory_percent": settings["gpu_memory_percent"],
        }
        current = c.execute(
            "SELECT * FROM jobs WHERE server_id=? AND gpu=? AND status IN ('STARTING','RUNNING')",
            (server["id"], gpu["uuid"]),
        ).fetchall()
        available = max(0, headroom_mb(gpu, limits, current))
        eligible = (
            online
            and not server["quarantined"]
            and cfg["enabled"]
            and cfg["institutional_permission"]
            and not settings["paused"]
            and settings["default_envs"] <= limits["max_envs"]
        )
        eligible = (
            eligible
            and (not inv.get("institutional_scheduler") or cfg["mode"] == "slurm")
            and (cfg["mode"] != "slurm" or bool(inv.get("slurm_job_id")))
        )
        eligible = eligible and (
            not cfg["mps_required"]
            or (cfg["mps_enabled"] and inv.get("mps", {}).get("ready"))
        )
        count = (
            min(
                remaining,
                max(0, limits["max_jobs"] - len(current)),
                int(available // expected),
            )
            if eligible
            else 0
        )
        result.append(
            {
                "gpu": gpu["uuid"],
                "available_mb": available,
                "additional_jobs": count,
                "num_envs": settings["default_envs"],
                "estimated_job_mb": expected,
                "memory_percent": settings["gpu_memory_percent"],
                "minimum_free_mb": minimum_free_mb(gpu, limits),
            }
        )
    return result


def schedule(db):
    with db.tx() as c:
        settings = db.settings(c)
        if settings["paused"]:
            return
        servers = c.execute(
            "SELECT * FROM servers WHERE quarantined=0 AND last_seen>?",
            (now() - db.cfg.heartbeat_timeout,),
        ).fetchall()
        jobs = c.execute(
            "SELECT * FROM jobs WHERE status='QUEUED' AND cancel=0 ORDER BY priority + (?-created)/600 DESC, created ASC",
            (now(),),
        ).fetchall()
        for job in jobs:
            running = c.execute(
                "SELECT count(*) FROM jobs WHERE status IN ('STARTING','RUNNING')"
            ).fetchone()[0]
            if running >= settings.get("max_running_jobs", 10):
                break
            spec = unpack(job["spec"])
            candidates = []
            for server in servers:
                cfg = unpack(server["config"])
                inv = unpack(server["inventory"])
                if (
                    not cfg["enabled"]
                    or not cfg["institutional_permission"]
                    or spec["num_envs"] > cfg["max_envs"]
                ):
                    continue
                if inv.get("institutional_scheduler") and cfg["mode"] != "slurm":
                    continue
                # Direct workers must run inside an institutional allocation if one is required.
                if cfg["mode"] == "slurm" and not inv.get("slurm_job_id"):
                    continue
                if cfg["mps_required"] and (
                    not cfg["mps_enabled"] or not inv.get("mps", {}).get("ready")
                ):
                    continue
                for gpu in inv.get("gpus", []):
                    limits = {**cfg, **cfg.get("gpu_limits", {}).get(gpu["uuid"], {})}
                    limits["gpu_memory_percent"] = settings["gpu_memory_percent"]
                    if spec["num_envs"] > limits["max_envs"]:
                        continue
                    current = c.execute(
                        "SELECT * FROM jobs WHERE server_id=? AND gpu=? AND status IN ('STARTING','RUNNING')",
                        (server["id"], gpu["uuid"]),
                    ).fetchall()
                    if len(current) >= limits["max_jobs"]:
                        continue
                    headroom = headroom_mb(gpu, limits, current)
                    if job["estimated_mb"] > headroom:
                        continue
                    candidates.append(
                        (
                            headroom - job["estimated_mb"],
                            server["id"],
                            gpu["uuid"],
                            pack(limits),
                        )
                    )
            if candidates:
                _, server_id, gpu, placement = min(
                    candidates
                )  # best fit preserves large contiguous capacity
                c.execute(
                    "UPDATE jobs SET status='STARTING',server_id=?,gpu=?,lease=?,started=?,placement=? WHERE id=? AND status='QUEUED'",
                    (server_id, gpu, uid(), now(), placement, job["id"]),
                )
                db.audit(
                    c,
                    "scheduler",
                    "admit",
                    {"job": job["id"], "server": server_id, "gpu": gpu},
                )


def public_job(row, c):
    d = dict(row)
    d["spec"] = unpack(d["spec"])
    d["execution"] = unpack(d["execution"]) if d["execution"] else None
    d.pop("lease", None)
    d["placement"] = unpack(d["placement"]) if d["placement"] else None
    user = c.execute("SELECT email FROM users WHERE id=?", (d["user_id"],)).fetchone()
    server = c.execute(
        "SELECT name FROM servers WHERE id=?", (d["server_id"],)
    ).fetchone()
    d["email"] = user[0]
    d["server_name"] = server[0] if server else None
    d["queue_position"] = None
    if d["status"] == "QUEUED":
        ids = [
            r[0]
            for r in c.execute(
                "SELECT id FROM jobs WHERE status='QUEUED' ORDER BY priority + (?-created)/600 DESC, created ASC",
                (now(),),
            )
        ]
        d["queue_position"] = ids.index(d["id"]) + 1
    return d
