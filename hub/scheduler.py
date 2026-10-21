"""Durable admission. Unknown/disconnected runs retain capacity and never auto-retry."""

import math
from .db import ACTIVE, now, pack, uid, unpack


def estimate(settings, spec):
    p = settings["memory_profiles"]
    return math.ceil(
        (p["base_mb"] + p["per_env_mb"] * spec["num_envs"]) * p["safety_factor"]
    )


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
                    if spec["num_envs"] > limits["max_envs"]:
                        continue
                    current = c.execute(
                        "SELECT * FROM jobs WHERE server_id=? AND gpu=? AND status IN ('STARTING','RUNNING')",
                        (server["id"], gpu["uuid"]),
                    ).fetchall()
                    if len(current) >= limits["max_jobs"]:
                        continue
                    # Account for measured clients and unmaterialized reservations without double counting.
                    measured = sum(j["gpu_mb"] for j in current)
                    external = max(0, gpu["total_mb"] - gpu["free_mb"] - measured)
                    committed = sum(
                        max(j["estimated_mb"], j["gpu_mb"]) for j in current
                    )
                    headroom = (
                        gpu["total_mb"]
                        - external
                        - committed
                        - limits["reserve_mb"]
                        - limits["margin_mb"]
                    )
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
