import asyncio
import fcntl
import re
import httpx
from contextlib import asynccontextmanager
import ipaddress
import json
import io
import zipfile
import logging
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import time
from urllib.parse import urlparse
from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.responses import (
    FileResponse,
    RedirectResponse,
    JSONResponse,
)
from fastapi.staticfiles import StaticFiles
from .config import Config, DEFAULT_SERVER, ROOT
from .db import DB, ACTIVE, digest, now, pack, uid, unpack
from .models import (
    Email,
    PasswordLogin,
    IssuePassword,
    SendPassword,
    EmailSettings,
    AddParticipant,
    ParticipantList,
    NewJob,
    UserEdit,
    Settings,
    NewServer,
    ServerConfig,
    Heartbeat,
    Report,
)
from .scheduler import schedule, estimate, public_job, server_capacity
from .snapshots import create_snapshot, safe_path, verify, zip_tree, sha

from .motions import (
    MAX_BYTES,
    store_motion,
    visible_motions,
    public_motion,
    robot_model,
)
from .passwords import verify_password, hash_password
from .tensorboard import TensorBoards
from .emailer import Mailer
from .policies import VERSION, obsolete_versions

log = logging.getLogger("hub")


def create_app(cfg=None):
    cfg = cfg or Config()
    db = DB(cfg)
    tensorboards = TensorBoards(cfg)
    mailer = Mailer(cfg)

    @asynccontextmanager
    async def lifespan(app):
        async def loop():
            while True:
                try:
                    await asyncio.to_thread(schedule, db)
                except Exception:
                    log.exception("Scheduler tick failed")
                await asyncio.sleep(2)

        task = asyncio.create_task(loop())
        yield
        task.cancel()
        tensorboards.close()
        try:
            await task
        except asyncio.CancelledError:
            pass

    app = FastAPI(title="Robot Training Hub", lifespan=lifespan)
    app.state.db = db
    app.state.cfg = cfg

    @app.middleware("http")
    async def security(request, call_next):
        if request.url.path.startswith("/api/") and request.method not in (
            "GET",
            "HEAD",
            "OPTIONS",
        ):
            origin = request.headers.get("origin")
            if origin and origin.rstrip("/") != cfg.public_url.rstrip("/"):
                allowed_alias = False
                if local_demo(request):
                    try:
                        candidate, expected = urlparse(origin), urlparse(cfg.public_url)
                        allowed_alias = (
                            candidate.hostname in {"localhost", "127.0.0.1", "::1"}
                            and candidate.scheme == expected.scheme
                            and candidate.port == expected.port
                        )
                    except ValueError:
                        pass
                if not allowed_alias:
                    return Response("Origin refused", status_code=403)
            if (
                not request.url.path.startswith("/api/worker/")
                and "/tensorboard/" not in request.url.path
                and request.headers.get("x-hub-request") != "1"
            ):
                return Response("X-Hub-Request required", status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        if "/tensorboard/" in request.url.path:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self' blob: data:; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'"
            )
            return response
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
        )
        return response

    def user(request: Request):
        token = request.cookies.get("hub_session", "")
        with db.connect() as c:
            row = c.execute(
                "SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.hash=? AND s.expires>?",
                (digest(token), now()),
            ).fetchone()
        if not row or not row["verified"] or not row["approved"]:
            raise HTTPException(401, "Login required")
        result = dict(row)
        result.pop("password_hash", None)
        return result

    def admin(u=Depends(user)):
        if u["role"] != "admin":
            raise HTTPException(403, "Administrator required")
        return u

    def worker(request: Request):
        token = request.headers.get("authorization", "").removeprefix("Bearer ")
        with db.connect() as c:
            row = c.execute(
                "SELECT * FROM servers WHERE token_hash=?", (digest(token),)
            ).fetchone()
        if not row:
            raise HTTPException(401, "Invalid worker credential")
        return dict(row)

    def get_job(c, key, u):
        row = c.execute("SELECT * FROM jobs WHERE id=?", (key,)).fetchone()
        if not row or (u["role"] != "admin" and row["user_id"] != u["id"]):
            raise HTTPException(404, "Run not found")
        return row

    def assigned(c, key, w, lease=None):
        row = c.execute(
            "SELECT * FROM jobs WHERE id=? AND server_id=?", (key, w["id"])
        ).fetchone()
        if not row or (
            lease is not None and not secrets.compare_digest(row["lease"] or "", lease)
        ):
            raise HTTPException(404, "Assignment not found")
        return row

    def mail_login(email, url):
        return mailer.send(
            email,
            "Sign in to Robot Training Hub",
            f"Sign in within 15 minutes:\n{url}\nIf you did not request this, ignore this email.",
            {"url": url, "created": now()},
        )

    def local_demo(request: Request):
        try:
            loopback = (
                request.client is not None
                and ipaddress.ip_address(request.client.host).is_loopback
            )
        except ValueError:
            loopback = False
        return (
            cfg.development
            and loopback
            and urlparse(cfg.public_url).hostname in {"localhost", "127.0.0.1", "::1"}
        )

    @app.get("/api/health")
    def health(request: Request):
        return {
            "ok": True,
            "development": cfg.development,
            "demo_login": local_demo(request),
            "name": "Robot Training Hub",
        }

    @app.post("/api/auth/demo")
    def demo_login(body: dict, request: Request, response: Response):
        if not local_demo(request):
            raise HTTPException(404, "Not found")
        role = body.get("role")
        if role not in ("admin", "participant"):
            raise HTTPException(422, "Choose an admin or participant demo")
        email = (
            "admin@workshop.example"
            if role == "admin"
            else "participant01@workshop.example"
        )
        with db.tx() as c:
            account = c.execute(
                "SELECT * FROM users WHERE email=? AND approved=1 AND role=?",
                (email, role),
            ).fetchone()
            if not account:
                raise HTTPException(
                    409,
                    "Demo accounts are unavailable. Start with scripts/demo.sh first.",
                )
            c.execute("UPDATE users SET verified=1 WHERE id=?", (account["id"],))
            token = secrets.token_urlsafe(32)
            c.execute(
                "INSERT INTO sessions VALUES(?,?,?)",
                (digest(token), account["id"], now() + cfg.session_seconds),
            )
            db.audit(c, account["id"], "local-demo-login", {"role": role})
        response.set_cookie(
            "hub_session",
            token,
            httponly=True,
            secure=cfg.public_url.startswith("https://"),
            samesite="strict",
            max_age=cfg.session_seconds,
        )
        return {"role": role, "redirect": "/admin" if role == "admin" else "/dashboard"}

    @app.post("/api/auth/password")
    def password_login(body: PasswordLogin, request: Request, response: Response):
        email = str(body.email).lower()
        key = (
            "password:"
            + email
            + ":"
            + (request.client.host if request.client else "unknown")
        )
        with db.tx() as c:
            limit = c.execute(
                "SELECT * FROM rate_limits WHERE key=?", (key,)
            ).fetchone()
            if limit and limit["at"] > now() - 900 and limit["count"] >= 8:
                raise HTTPException(429, "Too many attempts. Try again in 15 minutes.")
            c.execute(
                "INSERT INTO rate_limits VALUES(?,?,1) ON CONFLICT(key) DO UPDATE SET count=CASE WHEN at<? THEN 1 ELSE count+1 END,at=CASE WHEN at<? THEN excluded.at ELSE at END",
                (key, now(), now() - 900, now() - 900),
            )
            account = c.execute(
                "SELECT * FROM users WHERE email=? AND approved=1", (email,)
            ).fetchone()
        if (
            not account
            or not account["password_hash"]
            or not verify_password(body.password, account["password_hash"])
        ):
            raise HTTPException(401, "Email or password is incorrect")
        token = secrets.token_urlsafe(32)
        with db.tx() as c:
            current = c.execute(
                "SELECT * FROM users WHERE id=? AND approved=1 AND deleted_at IS NULL",
                (account["id"],),
            ).fetchone()
            if not current or current["password_hash"] != account["password_hash"]:
                raise HTTPException(
                    401, "Account access or password changed; sign in again"
                )
            c.execute(
                "INSERT INTO sessions VALUES(?,?,?)",
                (digest(token), account["id"], now() + cfg.session_seconds),
            )
            c.execute("UPDATE users SET verified=1 WHERE id=?", (account["id"],))
            c.execute("DELETE FROM rate_limits WHERE key=?", (key,))
        response.set_cookie(
            "hub_session",
            token,
            httponly=True,
            secure=cfg.public_url.startswith("https://"),
            samesite="strict",
            max_age=cfg.session_seconds,
        )
        return {"redirect": "/admin" if account["role"] == "admin" else "/dashboard"}

    @app.post("/api/auth/register")
    def register(body: Email):
        email = str(body.email).lower()
        with db.tx() as c:
            c.execute(
                "INSERT OR IGNORE INTO users(id,email,created) VALUES(?,?,?)",
                (uid(), email, now()),
            )
        return {
            "message": "Registration received. An administrator must approve your email before login."
        }

    @app.post("/api/auth/request")
    def request_login(body: Email, request: Request):
        email = str(body.email).lower()
        token = None
        with db.tx() as c:
            for key, limit in [
                ("email:" + email, 5),
                ("ip:" + (request.client.host if request.client else "unknown"), 30),
            ]:
                r = c.execute(
                    "SELECT * FROM rate_limits WHERE key=?", (key,)
                ).fetchone()
                if r and r["at"] > now() - 900 and r["count"] >= limit:
                    raise HTTPException(
                        429, "Please wait before requesting another link"
                    )
                c.execute(
                    "INSERT INTO rate_limits VALUES(?,?,1) ON CONFLICT(key) DO UPDATE SET count=CASE WHEN at<? THEN 1 ELSE count+1 END, at=CASE WHEN at<? THEN excluded.at ELSE at END",
                    (key, now(), now() - 900, now() - 900),
                )
            u = c.execute(
                "SELECT * FROM users WHERE email=? AND approved=1", (email,)
            ).fetchone()
            if u:
                token = secrets.token_urlsafe(32)
                c.execute("DELETE FROM magic WHERE user_id=?", (u["id"],))
                c.execute(
                    "INSERT INTO magic VALUES(?,?,?)",
                    (digest(token), u["id"], now() + 900),
                )
        if token:
            try:
                mail_login(email, f"{cfg.public_url}/login#token={token}")
            except Exception:
                log.error("SMTP delivery failed; check SMTP configuration")
                with db.tx() as c:
                    c.execute("DELETE FROM magic WHERE hash=?", (digest(token),))
                raise HTTPException(503, "Email delivery unavailable")
        return {"message": "If your email is approved, a sign-in link has been sent."}

    @app.post("/api/auth/verify")
    def verify_login(body: dict, response: Response):
        token = body.get("token", "")
        if not isinstance(token, str) or len(token) > 200:
            raise HTTPException(400, "Invalid link")
        with db.tx() as c:
            row = c.execute(
                "SELECT * FROM magic WHERE hash=? AND expires>?", (digest(token), now())
            ).fetchone()
            if not row:
                raise HTTPException(400, "Link expired or already used")
            u = c.execute(
                "SELECT * FROM users WHERE id=? AND approved=1", (row["user_id"],)
            ).fetchone()
            if not u:
                raise HTTPException(403, "Account not approved")
            c.execute("DELETE FROM magic WHERE hash=?", (digest(token),))
            c.execute("UPDATE users SET verified=1 WHERE id=?", (u["id"],))
            session = secrets.token_urlsafe(32)
            c.execute(
                "INSERT INTO sessions VALUES(?,?,?)",
                (digest(session), u["id"], now() + cfg.session_seconds),
            )
        response.set_cookie(
            "hub_session",
            session,
            httponly=True,
            secure=cfg.public_url.startswith("https://"),
            samesite="strict",
            max_age=cfg.session_seconds,
        )
        return {"ok": True}

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response):
        with db.tx() as c:
            c.execute(
                "DELETE FROM sessions WHERE hash=?",
                (digest(request.cookies.get("hub_session", "")),),
            )
        response.delete_cookie("hub_session")
        return {"ok": True}

    @app.get("/api/me")
    def me(u=Depends(user)):
        return u

    @app.get("/api/options")
    def options(u=Depends(user)):
        with db.connect() as c:
            s = db.settings(c)
            uploaded = visible_motions(c, u, approved_only=True)
        return {
            **s,
            "motions": s["motions"] + uploaded,
            "user_env_limit": u["env_limit"],
            "repository_url": "https://github.com/IntelligentRoboticsLab/booster_mjlab",
        }

    @app.get("/api/runs")
    def runs(status: str | None = None, q: str = "", u=Depends(user)):
        with db.connect() as c:
            rows = c.execute(
                "SELECT j.* FROM jobs j JOIN users u ON j.user_id=u.id WHERE (? OR j.user_id=?) AND (? IS NULL OR status=?) AND (name LIKE ? OR j.id LIKE ? OR u.email LIKE ?) ORDER BY created DESC LIMIT 500",
                (
                    u["role"] == "admin",
                    u["id"],
                    status,
                    status,
                    "%" + q + "%",
                    "%" + q + "%",
                    "%" + q + "%",
                ),
            ).fetchall()
            return [public_job(r, c) for r in rows]

    def submit(body, u):
        key = uid()
        with db.connect() as c:
            s = db.settings(c)
            if c.execute(
                "SELECT 1 FROM jobs WHERE user_id=? AND status IN ('QUEUED','STARTING','RUNNING')",
                (u["id"],),
            ).fetchone():
                raise HTTPException(409, "You already have an outstanding training run")
            if body.task not in s["tasks"]:
                raise HTTPException(422, "Task is not enabled for this workshop")
            limit = u["env_limit"] if u["env_limit"] is not None else s["max_envs"]
            if (
                body.num_envs not in s["presets"]
                or not s["min_envs"] <= body.num_envs <= limit
                or body.iterations > s["max_iterations"]
            ):
                raise HTTPException(
                    422, "Training size exceeds current workshop limits"
                )
            choices = s["motions"] + visible_motions(c, u, approved_only=True)
            motion = next((m for m in choices if m["id"] == body.motion_id), None)
            if not motion:
                raise HTTPException(422, "Select an approved motion")
            if (
                body.learning_rate is not None
                and not s["learning_rate_bounds"][0]
                <= body.learning_rate
                <= s["learning_rate_bounds"][1]
            ):
                raise HTTPException(422, "Learning rate outside approved range")
            for name, value in body.rewards.items():
                bounds = s["reward_bounds"].get(name)
                if not bounds or not bounds[0] <= value <= bounds[1]:
                    raise HTTPException(422, "Reward outside approved range")
            spec = {
                **body.model_dump(exclude={"motion_id"}),
                "motion": motion,
                "run_id": key,
            }
            try:
                checksum = create_snapshot(cfg, key, spec)
            except (OSError, ValueError) as e:
                raise HTTPException(503, str(e))
        with db.tx() as c:
            current = c.execute(
                "SELECT approved,env_limit FROM users WHERE id=?", (u["id"],)
            ).fetchone()
            if (
                not current
                or not current["approved"]
                or current["env_limit"] != u["env_limit"]
                or pack(db.settings(c)) != pack(s)
            ):
                raise HTTPException(
                    409,
                    "Workshop settings changed during preparation; please submit again",
                )
            c.execute(
                "INSERT INTO jobs(id,user_id,name,status,spec,created,estimated_mb,snapshot) VALUES(?,?,?,'QUEUED',?,?,?,?)",
                (
                    key,
                    u["id"],
                    body.name,
                    pack(spec),
                    now(),
                    estimate(s, spec),
                    checksum,
                ),
            )
            db.audit(c, u["id"], "submit", {"job": key})
            return public_job(
                c.execute("SELECT * FROM jobs WHERE id=?", (key,)).fetchone(), c
            )

    @app.post("/api/runs", status_code=201)
    def new_run(body: NewJob, u=Depends(user)):
        try:
            result = submit(body, u)
        except sqlite3.IntegrityError:
            raise HTTPException(409, "You already have an outstanding training run")
        schedule(db)
        return result

    @app.get("/api/runs/{key}")
    def run(key: str, u=Depends(user)):
        with db.connect() as c:
            r = get_job(c, key, u)
            data = public_job(r, c)
            data["metrics"] = [
                {"step": m["step"], **unpack(m["value"])}
                for m in c.execute(
                    "SELECT * FROM metrics WHERE job_id=? ORDER BY step DESC LIMIT 1000",
                    (key,),
                )
            ][::-1]
            data["tensorboard_available"] = (
                cfg.data / "tensorboard" / key
            ).exists() and any(
                (cfg.data / "tensorboard" / key).glob("events.out.tfevents*")
            )
            data["artifacts"] = [
                dict(a)
                for a in c.execute(
                    "SELECT path,sha256,size FROM artifacts WHERE job_id=? ORDER BY path",
                    (key,),
                )
            ]
            if data["server_id"]:
                server = c.execute(
                    "SELECT last_seen,quarantined FROM servers WHERE id=?",
                    (data["server_id"],),
                ).fetchone()
                data["worker_online"] = (
                    server["last_seen"] > now() - cfg.heartbeat_timeout
                )
                data["quarantined"] = bool(server["quarantined"])
            return data

    @app.post("/api/runs/{key}/cancel")
    def cancel(key: str, u=Depends(user)):
        with db.tx() as c:
            r = get_job(c, key, u)
            if r["status"] == "QUEUED":
                c.execute(
                    "UPDATE jobs SET status='CANCELED',cancel=1,ended=? WHERE id=?",
                    (now(), key),
                )
            elif r["status"] in ACTIVE:
                c.execute("UPDATE jobs SET cancel=1 WHERE id=?", (key,))
            db.audit(c, u["id"], "cancel", {"job": key})
        return {"ok": True}

    @app.post("/api/admin/runs/{key}/retry", status_code=201)
    def retry(key: str, u=Depends(admin)):
        with db.connect() as c:
            r = get_job(c, key, u)
            if r["status"] != "FAILED":
                raise HTTPException(409, "Only confirmed failed runs can be retried")
            owner = dict(
                c.execute("SELECT * FROM users WHERE id=?", (r["user_id"],)).fetchone()
            )
            spec = unpack(r["spec"])
        if not owner["approved"]:
            raise HTTPException(409, "Participant is disabled")
        body = NewJob(
            **{k: v for k, v in spec.items() if k not in ("motion", "run_id")},
            motion_id=spec["motion"]["id"],
        )
        result = submit(body, owner)
        schedule(db)
        return result

    @app.post("/api/admin/runs/{key}/priority")
    def priority(key: str, body: dict, u=Depends(admin)):
        p = body.get("priority")
        if type(p) != int or not -100 <= p <= 100:
            raise HTTPException(422, "Priority must be -100 to 100")
        with db.tx() as c:
            r = get_job(c, key, u)
            if r["status"] != "QUEUED":
                raise HTTPException(409, "Only queued jobs can be reprioritized")
            c.execute("UPDATE jobs SET priority=? WHERE id=?", (p, key))
            db.audit(c, u["id"], "priority", {"job": key, "priority": p})
        return {"ok": True}

    def source_root(key, u):
        if key == "base":
            root = cfg.data / "snapshots/base"
            if not root.exists():
                with db.tx() as c:
                    if not root.exists():
                        create_snapshot(
                            cfg,
                            "base",
                            {
                                "task": "Mjlab-Tracking-Flat-Booster-K1",
                                "description": "Workshop baseline — no run yet",
                            },
                        )
            return root
        with db.connect() as c:
            r = get_job(c, key, u)
        root = cfg.data / "snapshots" / r["id"]
        verify(root, r["snapshot"])
        return root

    @app.get("/api/code/{key}/tree")
    def tree(key: str, u=Depends(user)):
        root = source_root(key, u)
        return {
            "files": [
                str(p.relative_to(root)) for p in sorted(root.rglob("*")) if p.is_file()
            ],
            "manifest": json.loads((root / "manifest.json").read_text()),
        }

    @app.get("/api/code/{key}/file")
    def code(key: str, path: str, u=Depends(user)):
        root = source_root(key, u)
        try:
            p = safe_path(root, path)
        except ValueError:
            raise HTTPException(400, "Invalid path")
        if not p.is_file() or p.stat().st_size > 1024 * 1024:
            raise HTTPException(404, "Text file unavailable or too large")
        try:
            return {
                "path": path,
                "content": p.read_text(),
                "sha256": sha(p.read_bytes()),
            }
        except UnicodeDecodeError:
            raise HTTPException(415, "Binary asset; use source ZIP")

    @app.get("/api/code/{key}/download")
    def download_source(key: str, u=Depends(user)):
        root = source_root(key, u)
        return Response(
            zip_tree(root),
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="source-{key if key == "base" else root.name}.zip"'
            },
        )

    @app.get("/api/runs/{key}/logs")
    def logs(key: str, offset: int | None = None, u=Depends(user)):
        with db.connect() as c:
            r = get_job(c, key, u)
        path = cfg.data / "runs" / r["id"] / "training.log"
        if not path.exists():
            return {"text": "", "offset": 0}
        with path.open("rb") as f:
            f.seek(
                max(0, path.stat().st_size - 128 * 1024)
                if offset is None
                else max(0, min(offset, path.stat().st_size))
            )
            data = f.read(128 * 1024)
            return {"text": data.decode(errors="replace"), "offset": f.tell()}

    @app.get("/api/runs/{key}/logs/download")
    def download_logs(key: str, u=Depends(user)):
        with db.connect() as c:
            r = get_job(c, key, u)
        path = cfg.data / "runs" / r["id"] / "training.log"
        if not path.exists():
            raise HTTPException(404, "No logs yet")
        return FileResponse(path, filename=f"{key}.log", media_type="text/plain")

    @app.get("/api/runs/{key}/artifacts")
    def artifact(key: str, path: str, u=Depends(user)):
        with db.connect() as c:
            r = get_job(c, key, u)
            if not c.execute(
                "SELECT 1 FROM artifacts WHERE job_id=? AND path=?", (key, path)
            ).fetchone():
                raise HTTPException(404, "Artifact not found")
        return FileResponse(
            safe_path(cfg.data / "runs" / r["id"] / "artifacts", path),
            filename=Path(path).name,
            media_type="application/octet-stream",
        )

    @app.get("/api/admin/overview")
    def overview(u=Depends(admin)):
        with db.connect() as c:
            counts = {
                r["status"]: r["n"]
                for r in c.execute("SELECT status,count(*) n FROM jobs GROUP BY status")
            }
            return {
                "coordinator_host": socket.gethostname(),
                "participants": c.execute(
                    "SELECT count(*) FROM users WHERE role='participant' AND deleted_at IS NULL"
                ).fetchone()[0],
                "jobs": counts,
                "settings": db.settings(c),
                "audit": [
                    dict(r)
                    for r in c.execute("SELECT * FROM audit ORDER BY id DESC LIMIT 30")
                ],
            }

    @app.get("/api/admin/users")
    def users(u=Depends(admin)):
        with db.connect() as c:
            return [
                {k: r[k] for k in r.keys() if k != "password_hash"}
                for r in c.execute(
                    "SELECT * FROM users WHERE deleted_at IS NULL ORDER BY created"
                )
            ]

    @app.post("/api/admin/users")
    def allow(body: AddParticipant, u=Depends(admin)):
        with db.tx() as c:
            c.execute(
                "INSERT INTO users(id,email,approved,created) VALUES(?,?,1,?) ON CONFLICT(email) DO UPDATE SET approved=1,deleted_at=NULL",
                (uid(), str(body.email).lower(), now()),
            )
            if body.env_limit is not None:
                c.execute(
                    "UPDATE users SET env_limit=? WHERE email=?",
                    (body.env_limit, str(body.email).lower()),
                )
            db.audit(c, u["id"], "allow", {"email": str(body.email)})
        return {"ok": True}

    @app.put("/api/admin/users/{key}")
    def edit_user(key: str, body: UserEdit, u=Depends(admin)):
        if key == u["id"] and (body.role != "admin" or not body.approved):
            raise HTTPException(409, "Cannot disable your own administrator account")
        with db.tx() as c:
            if not c.execute(
                "SELECT 1 FROM users WHERE id=? AND deleted_at IS NULL", (key,)
            ).fetchone():
                raise HTTPException(404, "Account not found")
            c.execute(
                "UPDATE users SET approved=?,role=?,env_limit=? WHERE id=?",
                (body.approved, body.role, body.env_limit, key),
            )
            db.audit(c, u["id"], "edit-user", {"user": key, **body.model_dump()})
        return {"ok": True}

    @app.delete("/api/admin/users/{key}")
    def delete_participant(key: str, u=Depends(admin)):
        with db.tx() as c:
            target = c.execute(
                "SELECT * FROM users WHERE id=? AND deleted_at IS NULL", (key,)
            ).fetchone()
            if not target:
                raise HTTPException(404, "Participant not found")
            if target["role"] != "participant":
                raise HTTPException(
                    409, "Administrator accounts cannot be deleted here"
                )
            c.execute(
                "UPDATE users SET approved=0,deleted_at=?,password_hash=NULL WHERE id=?",
                (now(), key),
            )
            c.execute("DELETE FROM sessions WHERE user_id=?", (key,))
            c.execute("DELETE FROM magic WHERE user_id=?", (key,))
            c.execute(
                "UPDATE jobs SET status='CANCELED',cancel=1,ended=? WHERE user_id=? AND status='QUEUED'",
                (now(), key),
            )
            c.execute(
                "UPDATE jobs SET cancel=1 WHERE user_id=? AND status IN ('STARTING','RUNNING')",
                (key,),
            )
            db.audit(c, u["id"], "delete-participant", {"user": key})
        return {"ok": True, "history_preserved": True}

    @app.post("/api/admin/users/{key}/password")
    def issue_password(key: str, body: IssuePassword, u=Depends(admin)):
        password = secrets.token_urlsafe(18)
        password_hash = hash_password(password)
        with db.tx() as c:
            target = c.execute(
                "SELECT * FROM users WHERE id=? AND approved=1 AND deleted_at IS NULL",
                (key,),
            ).fetchone()
            if not target:
                raise HTTPException(404, "Approved participant not found")
            if target["role"] != "participant":
                raise HTTPException(
                    409,
                    "Use the administrator password reset command for admin accounts",
                )
            c.execute(
                "UPDATE users SET password_hash=?,credential_email_at=NULL WHERE id=?",
                (password_hash, key),
            )
            c.execute("DELETE FROM sessions WHERE user_id=?", (key,))
            c.execute("DELETE FROM magic WHERE user_id=?", (key,))
            db.audit(
                c,
                u["id"],
                "issue-participant-password",
                {"user": key, "email_requested": body.send_email},
            )
        delivery = "not_requested"
        if body.send_email:
            try:
                delivery = mailer.send(
                    target["email"],
                    "Your Robot Training Hub account",
                    f"Your workshop account is ready.\n\nSign in: {cfg.public_url}/login\nEmail: {target['email']}\nPassword: {password}\n\nKeep this password private. This replaces any previous workshop password.",
                )
            except Exception:
                delivery = "failed"
                log.error("Participant credential email was not confirmed by SMTP")
            if delivery == "sent":
                with db.tx() as c:
                    c.execute(
                        "UPDATE users SET credential_email_at=? WHERE id=? AND password_hash=? AND deleted_at IS NULL",
                        (now(), key, password_hash),
                    )
        with db.tx() as c:
            db.audit(
                c,
                u["id"],
                "participant-password-delivery",
                {"user": key, "status": delivery},
            )
        return {
            "user_id": key,
            "email": target["email"],
            "password": password,
            "delivery": delivery,
            "url": cfg.public_url + "/login",
        }

    @app.post("/api/admin/users/{key}/password/email")
    def email_existing_password(key: str, body: SendPassword, u=Depends(admin)):
        with db.connect() as c:
            target = c.execute(
                "SELECT * FROM users WHERE id=? AND approved=1 AND deleted_at IS NULL AND role='participant'",
                (key,),
            ).fetchone()
        if not target:
            raise HTTPException(404, "Approved participant not found")
        if not target["password_hash"] or not verify_password(
            body.password, target["password_hash"]
        ):
            raise HTTPException(
                409,
                "That password is no longer current. Generate a new password before emailing it.",
            )
        delivery = "failed"
        try:
            delivery = mailer.send(
                target["email"],
                "Your Robot Training Hub account",
                f"Your workshop account is ready.\n\nSign in: {cfg.public_url}/login\nEmail: {target['email']}\nPassword: {body.password}\n\nKeep this password private.",
            )
        except Exception:
            log.error("Participant credential email was not confirmed by SMTP")
        with db.tx() as c:
            if delivery == "sent":
                c.execute(
                    "UPDATE users SET credential_email_at=? WHERE id=? AND password_hash=? AND deleted_at IS NULL",
                    (now(), key, target["password_hash"]),
                )
            db.audit(
                c,
                u["id"],
                "email-existing-participant-password",
                {"user": key, "status": delivery},
            )
        return {"user_id": key, "email": target["email"], "delivery": delivery}

    @app.get("/api/admin/email")
    def email_status(u=Depends(admin)):
        return mailer.status()

    @app.put("/api/admin/email")
    def configure_email(body: EmailSettings, u=Depends(admin)):
        try:
            mailer.save(body.model_dump(mode="json"))
        except Exception:
            raise HTTPException(
                502,
                "SMTP connection or login failed. Check the server, account, and app password.",
            )
        with db.tx() as c:
            db.audit(
                c,
                u["id"],
                "configure-email",
                {"host": body.host, "sender": str(body.sender)},
            )
        return mailer.status()

    @app.post("/api/admin/email/test")
    def test_email(u=Depends(admin)):
        try:
            delivery = mailer.send(
                u["email"],
                "Robot Training Hub email test",
                "Email delivery from Robot Training Hub is working.\n" + cfg.public_url,
            )
        except Exception:
            raise HTTPException(
                502, "The mail server did not confirm sending the test email."
            )
        return {"delivery": delivery, "recipient": u["email"]}

    @app.get("/api/admin/settings")
    def settings(u=Depends(admin)):
        with db.connect() as c:
            return db.settings(c)

    @app.put("/api/admin/settings")
    def edit_settings(body: Settings, u=Depends(admin)):
        if not cfg.development and any(
            m.artifact.startswith("demo/") for m in body.motions
        ):
            raise HTTPException(422, "Demo motions are unavailable in production")
        with db.tx() as c:
            c.execute(
                "UPDATE settings SET value=? WHERE id=1", (pack(body.model_dump()),)
            )
            db.audit(c, u["id"], "settings", body.model_dump())
        return {"ok": True}

    @app.get("/api/admin/servers")
    def servers(u=Depends(admin)):
        with db.connect() as c:
            settings = db.settings(c)
            result = []
            for r in c.execute("SELECT * FROM servers ORDER BY name"):
                d = dict(r)
                d.pop("token_hash")
                d["config"] = unpack(d["config"])
                d["inventory"] = unpack(d["inventory"])
                d["online"] = d["last_seen"] > now() - cfg.heartbeat_timeout
                d["capacity"] = server_capacity(c, r, settings, d["online"])
                d["active_jobs"] = c.execute(
                    "SELECT count(*) FROM jobs WHERE server_id=? AND status IN ('STARTING','RUNNING')",
                    (d["id"],),
                ).fetchone()[0]
                result.append(d)
            return result

    @app.post("/api/admin/servers", status_code=201)
    def add_server(body: NewServer, u=Depends(admin)):
        token = secrets.token_urlsafe(40)
        key = uid()
        try:
            with db.tx() as c:
                c.execute(
                    "INSERT INTO servers(id,name,token_hash,config) VALUES(?,?,?,?)",
                    (key, body.name, digest(token), pack(body.config.model_dump())),
                )
                db.audit(c, u["id"], "add-server", {"server": key, "name": body.name})
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Server name already exists")
        return {
            "id": key,
            "token": token,
            "message": "Save this token securely; it will not be shown again",
        }

    @app.put("/api/admin/servers/{key}")
    def edit_server(key: str, body: ServerConfig, u=Depends(admin)):
        with db.tx() as c:
            if not c.execute("SELECT 1 FROM servers WHERE id=?", (key,)).fetchone():
                raise HTTPException(404, "Server not found")
            c.execute(
                "UPDATE servers SET config=? WHERE id=?", (pack(body.model_dump()), key)
            )
            db.audit(c, u["id"], "server-config", {"server": key, **body.model_dump()})
        return {"ok": True}

    @app.post("/api/admin/servers/{key}/reconcile")
    def reconcile(key: str, body: dict, u=Depends(admin)):
        if body.get("confirmed_all_processes_stopped") is not True:
            raise HTTPException(
                422,
                "Confirm all old workshop processes have stopped on this server first",
            )
        with db.tx() as c:
            c.execute(
                "UPDATE jobs SET status='FAILED',ended=?,error='Administrator confirmed worker processes stopped' WHERE server_id=? AND status IN ('STARTING','RUNNING')",
                (now(), key),
            )
            c.execute("UPDATE servers SET quarantined=0 WHERE id=?", (key,))
            db.audit(c, u["id"], "reconcile-confirmed-stopped", {"server": key})
        return {"ok": True}

    @app.post("/api/worker/heartbeat")
    def heartbeat(body: Heartbeat, w=Depends(worker)):
        with db.tx() as c:
            row = c.execute("SELECT * FROM servers WHERE id=?", (w["id"],)).fetchone()
            active = c.execute(
                "SELECT id,acknowledged FROM jobs WHERE server_id=? AND status IN ('STARTING','RUNNING')",
                (w["id"],),
            ).fetchall()
            restart = row["boot_id"] and row["boot_id"] != body.boot_id and active
            missing = any(
                r["acknowledged"] and r["id"] not in body.active for r in active
            )
            quarantined = bool(
                row["quarantined"] or restart or missing or body.unresolved
            )
            if body.inventory.mock and not cfg.development:
                raise HTTPException(403, "Mock workers require development mode")
            c.execute(
                "UPDATE servers SET inventory=?,last_seen=?,boot_id=?,quarantined=? WHERE id=?",
                (
                    pack(body.inventory.model_dump()),
                    now(),
                    body.boot_id,
                    quarantined,
                    w["id"],
                ),
            )
            config = unpack(row["config"])
        schedule(db)
        with db.connect() as c:
            jobs = [
                dict(r)
                for r in c.execute(
                    "SELECT * FROM jobs WHERE server_id=? AND status IN ('STARTING','RUNNING')",
                    (w["id"],),
                )
            ]
        return {
            "config": config,
            "quarantined": quarantined,
            "assignments": [
                {
                    "id": j["id"],
                    "lease": j["lease"],
                    "snapshot": j["snapshot"],
                    "gpu": j["gpu"],
                    "estimated_mb": j["estimated_mb"],
                    "spec": unpack(j["spec"]),
                    "cancel": bool(j["cancel"]),
                    "acknowledged": bool(j["acknowledged"]),
                    "config": unpack(j["placement"]) if j["placement"] else config,
                }
                for j in jobs
            ],
        }

    @app.post("/api/worker/runs/{key}/claim")
    def claim(key: str, body: dict, w=Depends(worker)):
        with db.tx() as c:
            r = assigned(c, key, w, body.get("lease", ""))
            server = c.execute(
                "SELECT * FROM servers WHERE id=?", (w["id"],)
            ).fetchone()
            if server["quarantined"] or r["acknowledged"] or r["status"] != "STARTING":
                raise HTTPException(409, "Assignment cannot be claimed")
            c.execute(
                "UPDATE jobs SET acknowledged=1,last_report=? WHERE id=?", (now(), key)
            )
        return {"cancel": bool(r["cancel"])}

    @app.get("/api/worker/runs/{key}/source")
    def worker_source(key: str, w=Depends(worker)):
        with db.connect() as c:
            r = assigned(c, key, w)
        root = cfg.data / "snapshots" / r["id"]
        verify(root, r["snapshot"])
        return Response(zip_tree(root), media_type="application/zip")

    @app.post("/api/worker/runs/{key}/report")
    def report(key: str, body: Report, w=Depends(worker)):
        with db.tx() as c:
            r = assigned(c, key, w, body.lease)
            if r["status"] not in ACTIVE:
                return {"cancel": bool(r["cancel"]), "terminal": True}
            if not r["acknowledged"]:
                raise HTTPException(409, "Claim assignment before reporting")
            if body.iteration > unpack(r["spec"])["iterations"]:
                raise HTTPException(422, "Iteration exceeds requested duration")
            if body.execution and len(pack(body.execution)) > 32768:
                raise HTTPException(413, "Execution metadata too large")
            if body.status == "COMPLETED" and (
                not body.execution and not r["execution"]
            ):
                raise HTTPException(422, "Execution manifest required")
            directory = cfg.data / "runs" / key
            directory.mkdir(parents=True, exist_ok=True)
            # Idempotent log chunks: retrying a report never duplicates text.
            seq_file = directory / "log_sequence.json"
            last = json.loads(seq_file.read_text()) if seq_file.exists() else -1
            if body.logs and body.log_seq > last:
                with (directory / "training.log").open("a") as f:
                    f.write(body.logs)
                temp = directory / "log_sequence.tmp"
                temp.write_text(str(body.log_seq))
                temp.replace(seq_file)
            status = body.status
            if r["cancel"] and status == "COMPLETED":
                status = "CANCELED"
            c.execute(
                "UPDATE jobs SET status=?,iteration=max(iteration,?),gpu_mb=?,last_report=?,error=?,execution=COALESCE(?,execution),ended=? WHERE id=?",
                (
                    status,
                    body.iteration,
                    body.gpu_mb,
                    now(),
                    body.error,
                    pack(body.execution) if body.execution else None,
                    now() if status not in ACTIVE else None,
                    key,
                ),
            )
            if body.metrics:
                c.execute(
                    "INSERT INTO metrics VALUES(?,?,?) ON CONFLICT(job_id,step) DO UPDATE SET value=excluded.value",
                    (key, body.iteration, pack(body.metrics)),
                )
            if status not in ACTIVE:
                db.audit(c, w["id"], "finish", {"job": key, "status": status})
            return {"cancel": bool(r["cancel"]), "terminal": status not in ACTIVE}

    @app.put("/api/worker/runs/{key}/artifact")
    async def upload(key: str, path: str, request: Request, w=Depends(worker)):
        versioned_policy = bool(VERSION.fullmatch(path))
        with db.connect() as c:
            r = assigned(c, key, w, request.headers.get("x-job-lease", ""))
            if r["status"] not in ACTIVE and not (
                versioned_policy and r["acknowledged"]
            ):
                raise HTTPException(409, "Run already finalized")
            used = c.execute(
                "SELECT COALESCE(sum(size),0) FROM artifacts WHERE job_id=?", (key,)
            ).fetchone()[0]
        if (
            not path.endswith((".pt", ".onnx", ".json", ".yaml", ".yml", ".txt"))
            or len(path) > 250
        ):
            raise HTTPException(422, "Artifact type refused")
        root = cfg.data / "runs" / r["id"] / "artifacts"
        try:
            target = safe_path(root, path)
        except ValueError:
            raise HTTPException(400, "Invalid path")
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(target.name + "." + uid() + ".part")
        size = 0
        expired = []
        try:
            with temp.open("wb") as f:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > cfg.artifact_limit or (
                        not versioned_policy and used + size > 2 * 1024 * 1024 * 1024
                    ):
                        raise HTTPException(413, "Artifact quota exceeded")
                    f.write(chunk)
            checksum = await asyncio.to_thread(lambda: sha(temp.read_bytes()))
            with db.tx() as c:
                # Completion is serialized with publication of the artifact index.
                current = assigned(c, key, w, request.headers.get("x-job-lease", ""))
                if current["status"] not in ACTIVE and not (
                    versioned_policy and current["acknowledged"]
                ):
                    raise HTTPException(409, "Run finalized while uploading")
                if c.execute(
                    "SELECT 1 FROM artifacts WHERE job_id=? AND path=?", (key, path)
                ).fetchone():
                    existing = c.execute(
                        "SELECT sha256 FROM artifacts WHERE job_id=? AND path=?",
                        (key, path),
                    ).fetchone()[0]
                    if existing != checksum:
                        raise HTTPException(409, "Published artifacts are immutable")
                else:
                    expired = []
                    if versioned_policy:
                        try:
                            expired = obsolete_versions(
                                c.execute(
                                    "SELECT path FROM artifacts WHERE job_id=?", (key,)
                                ).fetchall(),
                                path,
                            )
                        except ValueError as exc:
                            raise HTTPException(409, str(exc))
                        for old in expired:
                            c.execute(
                                "DELETE FROM artifacts WHERE job_id=? AND path=?",
                                (key, old),
                            )
                    published = c.execute(
                        "SELECT COALESCE(sum(size),0) FROM artifacts WHERE job_id=?",
                        (key,),
                    ).fetchone()[0]
                    if published + size > 2 * 1024 * 1024 * 1024:
                        raise HTTPException(413, "Artifact quota exceeded")
                    temp.replace(target)
                    target.chmod(0o444)
                    c.execute(
                        "INSERT INTO artifacts VALUES(?,?,?,?)",
                        (key, path, checksum, size),
                    )
            for old in expired:
                safe_path(root, old).unlink(missing_ok=True)
        finally:
            temp.unlink(missing_ok=True)
        return {"sha256": checksum, "size": size}

    @app.get("/api/worker/runs/{key}/policy-context")
    def policy_context(key: str, request: Request, w=Depends(worker)):
        with db.connect() as c:
            r = assigned(c, key, w, request.headers.get("x-job-lease", ""))
            if not r["acknowledged"]:
                raise HTTPException(409, "Run not claimed")
            return {
                "snapshot": r["snapshot"],
                "spec": unpack(r["spec"]),
                "status": r["status"],
            }

    @app.get("/api/policies")
    def list_policies(u=Depends(user)):
        with db.connect() as c:
            rows = c.execute(
                "SELECT a.*,j.name,j.status,j.spec,j.created,j.iteration,u.email,s.name server_name FROM artifacts a JOIN jobs j ON j.id=a.job_id JOIN users u ON u.id=j.user_id LEFT JOIN servers s ON s.id=j.server_id WHERE a.path LIKE '%.onnx' AND (? OR j.user_id=?) ORDER BY j.created DESC,a.path DESC LIMIT 1000",
                (u["role"] == "admin", u["id"]),
            ).fetchall()
            checkpoint_rows = c.execute(
                "SELECT job_id,path FROM artifacts WHERE path LIKE '%.pt'"
            ).fetchall()
        checkpoints = {}
        for item in checkpoint_rows:
            match = re.search(r"model_(\d+)\.pt$", item["path"])
            if match:
                checkpoints[(item["job_id"], int(match.group(1)))] = item["path"]
        result = []
        for row in rows:
            data = dict(row)
            spec = unpack(data.pop("spec"))
            data["motion"] = spec["motion"]["label"]
            data["policy_interval"] = spec.get("policy_interval", 100)
            match = VERSION.fullmatch(data["path"])
            data["iteration_index"] = int(match.group(2)) if match else None
            data["checkpoint_path"] = checkpoints.get(
                (data["job_id"], data["iteration_index"])
            )
            result.append(data)
        return result

    @app.get("/api/runs/{key}/policies/export")
    def export_policy(key: str, path: str, u=Depends(user)):
        with db.connect() as c:
            r = get_job(c, key, u)
            artifact = c.execute(
                "SELECT * FROM artifacts WHERE job_id=? AND path=?", (key, path)
            ).fetchone()
            configs = c.execute(
                "SELECT * FROM artifacts WHERE job_id=? AND (path LIKE '%.yaml' OR path LIKE '%.yml')",
                (key,),
            ).fetchall()
        if not artifact or not path.endswith(".onnx"):
            raise HTTPException(404, "Policy not available")
        root = cfg.data / "runs" / key / "artifacts"
        raw = safe_path(root, path).read_bytes()
        if sha(raw) != artifact["sha256"]:
            raise HTTPException(409, "Policy checksum mismatch")
        buffer = io.BytesIO()
        source_manifest = (cfg.data / "snapshots" / key / "manifest.json").read_bytes()
        if sha(source_manifest) != r["snapshot"]:
            raise HTTPException(409, "Source manifest checksum mismatch")
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("policy.onnx", raw)
            archive.writestr(
                "manifest.json",
                pack(
                    {
                        "run_id": key,
                        "policy_sha256": artifact["sha256"],
                        "snapshot_sha256": r["snapshot"],
                        "training_commits": json.loads(source_manifest)["commits"],
                        "configuration": unpack(r["spec"]),
                        "policy_path": path,
                    }
                ),
            )
            for item in configs:
                content = safe_path(root, item["path"]).read_bytes()
                if sha(content) != item["sha256"]:
                    raise HTTPException(409, "Configuration checksum mismatch")
                archive.writestr("config/" + item["path"], content)
        return Response(
            buffer.getvalue(),
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="policy-{key[:8]}.zip"'
            },
        )

    @app.post("/api/admin/users/bulk")
    def bulk_users(body: ParticipantList, u=Depends(admin)):
        with db.tx() as c:
            for email in dict.fromkeys(str(e).lower() for e in body.emails):
                c.execute(
                    "INSERT INTO users(id,email,approved,env_limit,created) VALUES(?,?,1,?,?) ON CONFLICT(email) DO UPDATE SET approved=1,deleted_at=NULL,env_limit=excluded.env_limit",
                    (uid(), email, body.env_limit, now()),
                )
            db.audit(c, u["id"], "approve-participants", {"count": len(body.emails)})
            user_ids = [
                c.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()[0]
                for email in dict.fromkeys(str(e).lower() for e in body.emails)
            ]
        return {"ok": True, "count": len(user_ids), "user_ids": user_ids}

    @app.post("/api/admin/users/{key}/invite")
    def invite(key: str, u=Depends(admin)):
        token = secrets.token_urlsafe(32)
        with db.tx() as c:
            account = c.execute(
                "SELECT * FROM users WHERE id=? AND approved=1", (key,)
            ).fetchone()
            if not account:
                raise HTTPException(404, "Approved account not found")
            c.execute(
                "INSERT INTO magic VALUES(?,?,?)", (digest(token), key, now() + 900)
            )
        return {"url": cfg.public_url + "/login#token=" + token, "expires_in": 900}

    def get_motion(c, key, u):
        row = c.execute("SELECT * FROM motions WHERE id=?", (key,)).fetchone()
        if not row or not (
            u["role"] == "admin" or row["user_id"] == u["id"] or row["shared"]
        ):
            raise HTTPException(404, "Motion not found")
        return row

    @app.get("/api/motions")
    def motions(u=Depends(user)):
        with db.connect() as c:
            return visible_motions(c, u)

    @app.post("/api/motions", status_code=201)
    async def upload_motion(
        request: Request,
        label: str = "Uploaded motion",
        fps: float = 50,
        shared: bool = False,
        u=Depends(user),
    ):
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > MAX_BYTES:
                raise HTTPException(413, "CSV must be smaller than 20 MiB")
        try:
            return await asyncio.to_thread(
                store_motion, db, u, bytes(data), label, fps, shared
            )
        except ValueError as e:
            raise HTTPException(422, str(e))

    @app.get("/api/motions/{key}/preview")
    def preview_motion(key: str, u=Depends(user)):
        with db.connect() as c:
            row = get_motion(c, key, u)
        return FileResponse(
            cfg.data / "motions" / row["id"] / "preview.json",
            media_type="application/json",
        )

    @app.get("/api/motions/{key}/download")
    def download_motion(key: str, u=Depends(user)):
        with db.connect() as c:
            row = get_motion(c, key, u)
        return FileResponse(
            cfg.data / "motions" / row["id"] / "input.csv",
            filename=row["label"] + ".csv",
            media_type="text/csv",
        )

    @app.post("/api/admin/motions/{key}/approve")
    def approve_motion(key: str, body: dict, u=Depends(admin)):
        with db.tx() as c:
            get_motion(c, key, u)
            c.execute(
                "UPDATE motions SET approved=?,shared=? WHERE id=?",
                (bool(body.get("approved", True)), bool(body.get("shared", True)), key),
            )
        return {"ok": True}

    @app.get("/api/robot/model")
    def robot(u=Depends(user)):
        return robot_model(cfg)

    @app.get("/api/robot/meshes/{name}")
    def mesh(name: str, u=Depends(user)):
        model = robot_model(cfg)
        if name not in {v["file"] for v in model["meshes"].values()}:
            raise HTTPException(404, "Mesh not found")
        return FileResponse(
            cfg.base_repo / "src/booster_mjlab/robots/booster_k1/xmls/meshes" / name,
            media_type="application/octet-stream",
        )

    @app.get("/api/worker/runs/{key}/motion")
    def assigned_motion(key: str, w=Depends(worker)):
        with db.connect() as c:
            r = assigned(c, key, w)
        motion = unpack(r["spec"])["motion"]
        if not motion["artifact"].startswith("upload:"):
            raise HTTPException(404, "This run has no uploaded CSV")
        identifier = motion["artifact"].split(":")[1]
        if not re.fullmatch("[a-f0-9]{32}", identifier):
            raise HTTPException(404, "Motion not found")
        return FileResponse(
            cfg.data / "motions" / identifier / "input.csv", media_type="text/csv"
        )

    @app.put("/api/worker/runs/{key}/events")
    async def events(
        key: str, name: str, offset: int, request: Request, w=Depends(worker)
    ):
        with db.connect() as c:
            r = assigned(c, key, w, request.headers.get("x-job-lease", ""))
        if r["status"] not in ACTIVE:
            raise HTTPException(409, "Run is already finalized")
        if (
            not re.fullmatch(r"events\.out\.tfevents[.a-zA-Z0-9_-]{1,220}", name)
            or offset < 0
        ):
            raise HTTPException(422, "Invalid TensorBoard event file")
        folder = cfg.data / "tensorboard" / r["id"]
        folder.mkdir(parents=True, exist_ok=True)
        file = folder / name
        size = file.stat().st_size if file.exists() else 0
        payload = bytearray()
        async for chunk in request.stream():
            payload.extend(chunk)
            if (
                len(payload) > 2 * 1024 * 1024
                or offset + len(payload) > 128 * 1024 * 1024
            ):
                raise HTTPException(413, "TensorBoard upload quota exceeded")
        with file.open("ab") as target:
            fcntl.flock(target, fcntl.LOCK_EX)
            size = target.seek(0, 2)
            if offset != size:
                return JSONResponse({"offset": size}, status_code=409)
            target.write(payload)
            target.flush()
        return {"offset": file.stat().st_size}

    @app.get("/api/runs/{key}/tensorboard")
    def tensorboard_redirect(key: str, u=Depends(user)):
        with db.connect() as c:
            get_job(c, key, u)
        return RedirectResponse(f"/api/runs/{key}/tensorboard/")

    @app.api_route("/api/runs/{key}/tensorboard/{path:path}", methods=["GET", "POST"])
    async def tensorboard_proxy(key: str, path: str, request: Request, u=Depends(user)):
        with db.connect() as c:
            r = get_job(c, key, u)
        try:
            base = await asyncio.to_thread(tensorboards.url, r["id"])
        except ValueError as e:
            raise HTTPException(425, str(e))
        except RuntimeError as e:
            raise HTTPException(503, str(e))
        target = base + f"/api/runs/{key}/tensorboard/" + path
        if request.url.query:
            target += "?" + request.url.query
        payload = await request.body()
        if len(payload) > 2 * 1024 * 1024:
            raise HTTPException(413, "Request is too large")
        async with httpx.AsyncClient(timeout=20) as client:
            for attempt in range(30):
                try:
                    upstream = await client.request(
                        request.method,
                        target,
                        content=payload,
                        headers={
                            "Content-Type": request.headers.get(
                                "content-type", "application/octet-stream"
                            )
                        },
                    )
                    headers = {
                        k: v
                        for k, v in upstream.headers.items()
                        if k.lower()
                        not in {
                            "content-length",
                            "content-encoding",
                            "connection",
                            "transfer-encoding",
                            "set-cookie",
                        }
                    }
                    return Response(
                        upstream.content,
                        status_code=upstream.status_code,
                        headers=headers,
                    )
                except httpx.ConnectError:
                    await asyncio.sleep(0.1)
        raise HTTPException(503, "TensorBoard is starting. Refresh in a moment.")

    dist = ROOT / "frontend/dist"
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}")
        def frontend(path: str):
            if path.startswith("api/"):
                raise HTTPException(404, "API not found")
            return FileResponse(dist / "index.html")

    return app


app = create_app()
