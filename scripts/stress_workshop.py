"""Bounded real workshop stress test. Uses ordinary participant/admin APIs only.
Creates labeled temporary accounts, real queued GPU jobs, and parallel HTTP clients.
Never changes GPU reservations, concurrency limits, MPS, or other users' jobs.
"""

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import multiprocessing
from pathlib import Path
import statistics
import time
import uuid
import httpx

ACTIVE = {"QUEUED", "STARTING", "RUNNING"}


def percentile(values, p):
    if not values:
        return None
    return round(sorted(values)[min(len(values) - 1, int((len(values) - 1) * p))], 3)


def participant(case):
    url, token, name, motion, envs, iterations, deadline = case
    latencies = []
    job_id = None

    def request(c, method, path, **kwargs):
        start = time.monotonic()
        response = c.request(method, path, **kwargs)
        latencies.append(time.monotonic() - start)
        return response

    try:
        with httpx.Client(
            base_url=url, headers={"X-Hub-Request": "1"}, timeout=120
        ) as c:
            request(
                c, "POST", "/api/auth/verify", json={"token": token}
            ).raise_for_status()
            assert c.get("/api/admin/users").status_code == 403
            spec = {
                "name": name,
                "motion_id": motion,
                "num_envs": envs,
                "iterations": iterations,
            }
            response = request(c, "POST", "/api/runs", json=spec)
            response.raise_for_status()
            job_id = response.json()["id"]
            assert request(c, "POST", "/api/runs", json=spec).status_code == 409, (
                "Outstanding job rule failed"
            )
            first_queued = None
            started = time.monotonic()
            read_logs = False
            while time.monotonic() < deadline:
                response = request(c, "GET", "/api/runs/" + job_id)
                response.raise_for_status()
                job = response.json()
                if job["status"] == "QUEUED" and first_queued is None:
                    first_queued = time.monotonic()
                if job["status"] == "RUNNING" and not read_logs:
                    request(
                        c, "GET", "/api/runs/" + job_id + "/logs"
                    ).raise_for_status()
                    read_logs = True
                if job["status"] not in ACTIVE:
                    checkpoint = next(
                        (
                            a
                            for a in reversed(job.get("artifacts", []))
                            if a["path"].endswith(".pt")
                        ),
                        None,
                    )
                    verified = False
                    if job["status"] == "COMPLETED":
                        assert not job["execution"].get("mock")
                        assert job["iteration"] == iterations and checkpoint, (
                            "Missing completed progress/checkpoint"
                        )
                        download = request(
                            c,
                            "GET",
                            "/api/runs/" + job_id + "/artifacts",
                            params={"path": checkpoint["path"]},
                        )
                        download.raise_for_status()
                        verified = (
                            hashlib.sha256(download.content).hexdigest()
                            == checkpoint["sha256"]
                        )
                        assert verified, "Checkpoint checksum mismatch"
                    return {
                        "name": name,
                        "job_id": job_id,
                        "status": job["status"],
                        "server": job.get("server_name"),
                        "iterations": job["iteration"],
                        "checkpoint_verified": verified,
                        "error": job.get("error"),
                        "seconds": round(time.monotonic() - started, 2),
                        "requests": len(latencies),
                        "p95_seconds": percentile(latencies, 0.95),
                        "saw_queue": first_queued is not None,
                    }
                time.sleep(2)
            request(c, "POST", "/api/runs/" + job_id + "/cancel").raise_for_status()
            return {
                "name": name,
                "job_id": job_id,
                "status": "TIMEOUT",
                "error": "Deadline reached; cancellation requested",
                "requests": len(latencies),
            }
    except Exception as e:
        return {
            "name": name,
            "job_id": job_id,
            "status": "TEST_ERROR",
            "error": str(e),
            "requests": len(latencies),
        }


def traffic(case):
    url, seconds = case
    times = []
    codes = Counter()
    deadline = time.monotonic() + seconds
    with httpx.Client(base_url=url, timeout=30) as c:
        while time.monotonic() < deadline:
            start = time.monotonic()
            try:
                r = c.get("/api/health")
                codes[str(r.status_code)] += 1
            except httpx.HTTPError:
                codes["transport_error"] += 1
            times.append(time.monotonic() - start)
            time.sleep(max(0, 0.2 - (time.monotonic() - start)))
    return {
        "requests": len(times),
        "status_codes": dict(codes),
        "p50_seconds": percentile(times, 0.5),
        "p95_seconds": percentile(times, 0.95),
        "max_seconds": round(max(times), 3) if times else None,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url", required=True)
    p.add_argument(
        "--credentials", type=Path, default=Path("data/workshop/admin-credentials.txt")
    )
    p.add_argument("--participants", type=int, default=18)
    p.add_argument("--iterations", type=int, default=3)
    p.add_argument("--envs", type=int, default=1024)
    p.add_argument("--timeout", type=int, default=1800)
    p.add_argument("--traffic-processes", type=int, default=4)
    p.add_argument("--traffic-seconds", type=int, default=90)
    args = p.parse_args()
    if not args.url.startswith("https://"):
        p.error("Real stress tests require trusted HTTPS")
    if (
        not 2 <= args.participants <= 18
        or not 1 <= args.iterations <= 10
        or not 1 <= args.traffic_processes <= 8
        or not 10 <= args.traffic_seconds <= 180
        or not 60 <= args.timeout <= 1800
    ):
        p.error("Use bounded workshop test sizes")
    identity = (
        "stress-"
        + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        + "-"
        + uuid.uuid4().hex[:5]
    )
    folder = Path("data/stress") / identity
    folder.mkdir(parents=True, mode=0o700)
    values = dict(
        line.split(": ", 1)
        for line in args.credentials.read_text().splitlines()
        if ": " in line
    )
    admin = httpx.Client(base_url=args.url, headers={"X-Hub-Request": "1"}, timeout=120)
    admin.post(
        "/api/auth/password",
        json={"email": values["Email"], "password": values["Password"]},
    ).raise_for_status()
    settings = admin.get("/api/admin/settings").json()
    if settings["paused"]:
        raise SystemExit("Scheduling is paused; no stress jobs were created")
    if args.envs not in settings["presets"]:
        raise SystemExit("Environment count is not an approved preset")
    motion = next(
        (m for m in admin.get("/api/motions").json() if m["approved"] and m["shared"]),
        None,
    )
    if not motion:
        raise SystemExit("An approved shared real CSV motion is required")
    emails = [f"{identity}-{i:02}@example.org" for i in range(args.participants)]
    admin.post(
        "/api/admin/users/bulk", json={"emails": emails, "env_limit": args.envs}
    ).raise_for_status()
    accounts = {
        u["email"]: u
        for u in admin.get("/api/admin/users").json()
        if u["email"] in emails
    }
    deadline = time.monotonic() + args.timeout
    cases = []
    for i, email in enumerate(emails):
        invitation = admin.post("/api/admin/users/" + accounts[email]["id"] + "/invite")
        invitation.raise_for_status()
        token = invitation.json()["url"].split("token=")[1]
        cases.append(
            (
                args.url,
                token,
                f"{identity} · participant {i + 1:02}",
                motion["id"],
                args.envs,
                args.iterations,
                deadline,
            )
        )
    samples = []
    results = []
    traffic_results = []
    peak_active = 0
    peak_queued = 0
    violations = []
    last_print = 0
    started = time.monotonic()
    print(
        f"{identity}: {args.participants} real participants, {args.envs} environments, {args.iterations} iterations; global cap {settings['max_running_jobs']}, memory ceiling {settings['gpu_memory_percent']}%.",
        flush=True,
    )
    try:
        with ProcessPoolExecutor(
            max_workers=args.participants + args.traffic_processes,
            mp_context=multiprocessing.get_context("spawn"),
        ) as pool:
            futures = [pool.submit(participant, case) for case in cases]
            traffic_futures = [
                pool.submit(traffic, (args.url, args.traffic_seconds))
                for _ in range(args.traffic_processes)
            ]
            while not all(f.done() for f in futures):
                runs = admin.get("/api/runs", params={"q": identity}).json()
                counts = Counter(j["status"] for j in runs)
                all_runs = admin.get("/api/runs").json()
                active = sum(j["status"] in ("STARTING", "RUNNING") for j in all_runs)
                servers = admin.get("/api/admin/servers").json()
                peak_active = max(peak_active, active)
                peak_queued = max(peak_queued, counts["QUEUED"])
                sample = {
                    "seconds": round(time.monotonic() - started, 2),
                    "statuses": dict(counts),
                    "global_active": active,
                    "gpus": [],
                }
                if active > settings["max_running_jobs"]:
                    violations.append("Global active job cap exceeded")
                for server in servers:
                    for gpu in server["inventory"].get("gpus", []):
                        limits = {
                            **server["config"],
                            **server["config"]
                            .get("gpu_limits", {})
                            .get(gpu["uuid"], {}),
                        }
                        floor = max(
                            limits["reserve_mb"] + limits["margin_mb"],
                            gpu["total_mb"]
                            * (100 - settings["gpu_memory_percent"])
                            / 100,
                        )
                        item = {
                            "server": server["name"],
                            "gpu": gpu["uuid"],
                            "free_mb": gpu["free_mb"],
                            "total_mb": gpu["total_mb"],
                            "used_percent": round(
                                100 * (1 - gpu["free_mb"] / gpu["total_mb"]), 2
                            ),
                            "minimum_free_mb": round(floor),
                            "active_jobs": server["active_jobs"],
                            "online": server["online"],
                        }
                        sample["gpus"].append(item)
                        if server["active_jobs"] and gpu["free_mb"] < floor:
                            violations.append(
                                "Memory policy crossed on " + server["name"]
                            )
                samples.append(sample)
                (folder / "live.json").write_text(
                    json.dumps({"id": identity, "samples": samples}, indent=2)
                )
                if time.monotonic() - last_print > 15:
                    print(
                        f"{sample['seconds']:.0f}s: {dict(counts)}; {active} global active",
                        flush=True,
                    )
                    last_print = time.monotonic()
                if violations or time.monotonic() > deadline:
                    print(
                        "Stopping this test’s jobs safely:",
                        violations or "time limit",
                        flush=True,
                    )
                    for job in runs:
                        if job["status"] in ACTIVE:
                            admin.post(
                                "/api/runs/" + job["id"] + "/cancel"
                            ).raise_for_status()
                    break
                time.sleep(3)
            results = [f.result() for f in futures]
            traffic_results = [f.result() for f in traffic_futures]
    finally:
        current = admin.get("/api/runs", params={"q": identity}).json()
        for job in current:
            if job["status"] in ACTIVE:
                admin.post("/api/runs/" + job["id"] + "/cancel").raise_for_status()
        # Keep evidence/artifacts, but these synthetic attendees must not retain access.
        for account in accounts.values():
            admin.put(
                "/api/admin/users/" + account["id"],
                json={"approved": False, "role": "participant", "env_limit": args.envs},
            ).raise_for_status()
        report = {
            "id": identity,
            "url": args.url,
            "mode": "REAL_GPU",
            "participants": args.participants,
            "environments": args.envs,
            "iterations": args.iterations,
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "peak_global_active": peak_active,
            "peak_queued": peak_queued,
            "global_job_cap": settings["max_running_jobs"],
            "gpu_memory_ceiling_percent": settings["gpu_memory_percent"],
            "violations": sorted(set(violations)),
            "results": results,
            "traffic": traffic_results,
            "samples": samples,
            "temporary_accounts_disabled": True,
        }
        (folder / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
        print("Report: " + str(folder / "summary.json"), flush=True)
        admin.close()
    statuses = Counter(r["status"] for r in results)
    print("Final statuses:", dict(statuses), flush=True)
    if (
        len(results) != args.participants
        or statuses.get("COMPLETED") != args.participants
        or violations
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
