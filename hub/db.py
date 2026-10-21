import contextlib
import hashlib
import json
import secrets
import sqlite3
import time
from .config import DEFAULT_SETTINGS

ACTIVE = ("QUEUED", "STARTING", "RUNNING")


def now():
    return time.time()


def uid():
    return secrets.token_hex(16)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def pack(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def unpack(value):
    return json.loads(value)


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
 id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, role TEXT NOT NULL DEFAULT 'participant',
 approved INTEGER NOT NULL DEFAULT 0, verified INTEGER NOT NULL DEFAULT 0,
 env_limit INTEGER, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS magic (hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS servers (
 id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL, token_hash TEXT NOT NULL,
 config TEXT NOT NULL, inventory TEXT NOT NULL DEFAULT '{}', last_seen REAL NOT NULL DEFAULT 0,
 boot_id TEXT, quarantined INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS jobs (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), name TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('QUEUED','STARTING','RUNNING','COMPLETED','FAILED','CANCELED')),
 spec TEXT NOT NULL, created REAL NOT NULL, started REAL, ended REAL,
 priority INTEGER NOT NULL DEFAULT 0, server_id TEXT, gpu TEXT, estimated_mb INTEGER NOT NULL,
 iteration INTEGER NOT NULL DEFAULT 0, gpu_mb INTEGER NOT NULL DEFAULT 0,
 cancel INTEGER NOT NULL DEFAULT 0, error TEXT, lease TEXT, acknowledged INTEGER NOT NULL DEFAULT 0,
 snapshot TEXT NOT NULL, execution TEXT, last_report REAL, placement TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS one_outstanding ON jobs(user_id)
 WHERE status IN ('QUEUED','STARTING','RUNNING');
CREATE TABLE IF NOT EXISTS metrics (
 job_id TEXT NOT NULL, step INTEGER NOT NULL, value TEXT NOT NULL,
 PRIMARY KEY(job_id,step));
CREATE TABLE IF NOT EXISTS artifacts (
 job_id TEXT NOT NULL, path TEXT NOT NULL, sha256 TEXT NOT NULL, size INTEGER NOT NULL,
 PRIMARY KEY(job_id,path));
CREATE TABLE IF NOT EXISTS motions (
 id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),label TEXT NOT NULL,
 filename TEXT NOT NULL,fps REAL NOT NULL,frames INTEGER NOT NULL,duration REAL NOT NULL,
 sha256 TEXT NOT NULL,approved INTEGER NOT NULL DEFAULT 0,shared INTEGER NOT NULL DEFAULT 0,created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS audit (
 id INTEGER PRIMARY KEY, at REAL NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS rate_limits (key TEXT PRIMARY KEY, at REAL NOT NULL, count INTEGER NOT NULL);
"""


class DB:
    def __init__(self, cfg):
        if (cfg.data / ".hosted-on-workstation").exists():
            raise RuntimeError(
                "This is the pre-migration archive. The live coordinator runs on the Coordinator host; use the SSH preview or administer that host."
            )
        self.cfg = cfg
        cfg.data.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connect() as c:
            c.executescript(SCHEMA)
            columns = {row[1] for row in c.execute("PRAGMA table_info(users)")}
            if "password_hash" not in columns:
                c.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
            current = (
                unpack(c.execute("SELECT value FROM settings WHERE id=1").fetchone()[0])
                if c.execute("SELECT 1 FROM settings WHERE id=1").fetchone()
                else {}
            )
            for key in ("max_running_jobs", "gpu_memory_percent"):
                if key not in current and current:
                    current[key] = DEFAULT_SETTINGS[key]
                    c.execute(
                        "UPDATE settings SET value=? WHERE id=1", (pack(current),)
                    )
            c.execute(
                "INSERT OR IGNORE INTO settings VALUES (1,?)", (pack(DEFAULT_SETTINGS),)
            )

    def connect(self):
        c = sqlite3.connect(self.cfg.db, timeout=30, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA foreign_keys=ON")
        c.execute("PRAGMA busy_timeout=30000")
        return c

    @contextlib.contextmanager
    def tx(self):
        c = self.connect()
        try:
            c.execute("BEGIN IMMEDIATE")
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    def settings(self, c):
        return unpack(c.execute("SELECT value FROM settings WHERE id=1").fetchone()[0])

    def audit(self, c, actor, action, detail):
        c.execute(
            "INSERT INTO audit(at,actor,action,detail) VALUES(?,?,?,?)",
            (now(), actor, action, pack(detail)),
        )
