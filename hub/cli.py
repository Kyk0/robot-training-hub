import argparse
import json
import secrets
import subprocess
import os
from pathlib import Path
from .config import Config, DEFAULT_SERVER
from .db import DB, digest, now, pack, uid
from .passwords import hash_password


def provision_password(db, email, path):
    """Generate a password once; never print or pass the secret on a command line."""
    path = Path(path).resolve()
    password = secrets.token_urlsafe(27)
    encoded = hash_password(password)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        add_admin(db, email)
        with db.tx() as c:
            c.execute(
                "UPDATE users SET password_hash=? WHERE email=?",
                (encoded, email.lower()),
            )
            c.execute(
                "DELETE FROM sessions WHERE user_id=(SELECT id FROM users WHERE email=?)",
                (email.lower(),),
            )
        with os.fdopen(fd, "w") as f:
            f.write(
                f"Robot Training Hub\nURL: {db.cfg.public_url}/login\nEmail: {email.lower()}\nPassword: {password}\n\nKeep this file private. This password is not committed to Git.\n"
            )
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def add_admin(db, email):
    with db.tx() as c:
        c.execute(
            "INSERT INTO users(id,email,role,approved,created) VALUES(?,?,'admin',1,?) ON CONFLICT(email) DO UPDATE SET role='admin',approved=1,deleted_at=NULL",
            (uid(), email.lower(), now()),
        )


def login_link(db, email):
    token = secrets.token_urlsafe(32)
    with db.tx() as c:
        user = c.execute(
            "SELECT * FROM users WHERE email=? AND approved=1", (email.lower(),)
        ).fetchone()
        if not user:
            raise SystemExit("Account must be approved first")
        c.execute(
            "INSERT INTO magic VALUES(?,?,?)", (digest(token), user["id"], now() + 900)
        )
    return f"{db.cfg.public_url}/login#token={token}"


def seed(db, email, participants):
    if not db.cfg.development:
        raise SystemExit("Demo data requires HUB_DEVELOPMENT=1")
    add_admin(db, email)
    credentials = []
    with db.tx() as c:
        for i in range(1, participants + 1):
            c.execute(
                "INSERT OR IGNORE INTO users(id,email,approved,created) VALUES(?,?,1,?)",
                (uid(), f"participant{i:02}@workshop.example", now()),
            )
        s = db.settings(c)
        s["motions"] = [
            {
                "id": "demo-walk",
                "label": "Walking · simulated demo",
                "artifact": "demo/motions/walking:v0",
                "sha256": None,
            }
        ]
        c.execute("UPDATE settings SET value=? WHERE id=1", (pack(s),))
        for name, memory, reserve, max_jobs in [
            ("Coordinator host", 24576, 0, 1),
            ("Worker A", 95830, 46080, 3),
            ("Worker B", 95830, 46080, 3),
        ]:
            previous = c.execute(
                "SELECT * FROM servers WHERE name=?", (name,)
            ).fetchone()
            if previous:
                continue
            token = secrets.token_urlsafe(40)
            key = uid()
            config = {
                **DEFAULT_SERVER,
                "reserve_mb": reserve,
                "max_jobs": max_jobs,
                "institutional_permission": True,
                "gpu_limits": {},
                "mps_namespace": "",
            }
            c.execute(
                "INSERT INTO servers(id,name,token_hash,config) VALUES(?,?,?,?)",
                (key, name, digest(token), pack(config)),
            )
            credentials.append(
                {"id": key, "name": name, "token": token, "memory": memory}
            )
    root = db.cfg.data / "demo-workers"
    root.mkdir(exist_ok=True, mode=0o700)
    for item in credentials:
        path = root / (item["id"] + ".json")
        path.write_text(pack(item))
        path.chmod(0o600)
    return credentials


def main():
    p = argparse.ArgumentParser(
        description="Robot Training Hub administration (local filesystem access required)"
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("admin")
    a.add_argument("email")
    a = sub.add_parser(
        "admin-password",
        help="Generate a new private admin password file (never overwrites)",
    )
    a.add_argument("email")
    a.add_argument("--save", type=Path, required=True)
    a = sub.add_parser("login-link")
    a.add_argument("email")
    a = sub.add_parser("demo")
    a.add_argument("--admin", default="admin@workshop.example")
    a.add_argument("--participants", type=int, default=18)
    sub.add_parser("demo-workers")
    sub.add_parser("inspect")
    args = p.parse_args()
    cfg = Config()
    db = DB(cfg)
    if args.cmd == "admin-password":
        print(
            "Admin password saved privately to "
            + str(provision_password(db, args.email, args.save))
        )
    if args.cmd == "admin":
        add_admin(db, args.email)
        print(
            "Admin approved. Use website magic-link login with SMTP or the local login-link command."
        )
    if args.cmd == "login-link":
        print(login_link(db, args.email))
    if args.cmd == "demo":
        seed(db, args.admin, args.participants)
        print(
            f"Seeded {args.participants} participants. Admin sign-in link (15 minutes, single-use):\n"
            + login_link(db, args.admin)
        )
    if args.cmd == "inspect":
        from .hardware import discover

        print(json.dumps(discover(), indent=2))
    if args.cmd == "demo-workers":
        if not cfg.development:
            raise SystemExit("Demo workers require HUB_DEVELOPMENT=1")
        processes = []
        import signal

        try:
            for f in (cfg.data / "demo-workers").glob("*.json"):
                item = json.loads(f.read_text())
                token_file = f.with_suffix(".token")
                token_file.write_text(item["token"])
                token_file.chmod(0o600)
                processes.append(
                    subprocess.Popen(
                        [
                            str(Path(__import__("sys").executable)),
                            "-m",
                            "hub.worker",
                            "--coordinator",
                            cfg.public_url,
                            "--mock",
                            "--token-file",
                            str(token_file),
                            "--root",
                            str(cfg.data / "workers" / item["id"]),
                            "--mock-memory",
                            str(item["memory"]),
                            "--name",
                            item["name"].lower().replace(" ", "-"),
                        ]
                    )
                )

            def stop(*_):
                raise KeyboardInterrupt

            signal.signal(signal.SIGTERM, stop)
            for proc in processes:
                proc.wait()
        except KeyboardInterrupt:
            pass
        finally:
            for proc in processes:
                if proc.poll() is None:
                    proc.terminate()
            for proc in processes:
                proc.wait()


if __name__ == "__main__":
    main()
