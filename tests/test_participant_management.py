import json
import smtplib
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from conftest import enroll, heartbeat
from hub.cli import login_link
from hub.db import digest, pack
from hub.emailer import Mailer
from hub.passwords import verify_password
from hub.scheduler import schedule


def test_delete_participant_revokes_access_cancels_queue_and_preserves_history(
    setup, job
):
    app, db, cfg, client = setup
    admin, alice = client("admin@example.org"), client("alice@example.org")
    account = alice.get("/api/me").json()
    key = account["id"]
    token = login_link(db, account["email"]).split("token=")[1]
    run = alice.post("/api/runs", json=job).json()
    assert alice.delete("/api/admin/users/" + key).status_code == 403
    assert admin.delete("/api/admin/users/" + key).status_code == 200
    assert alice.get("/api/me").status_code == 401
    other = TestClient(app, headers={"X-Hub-Request": "1"})
    assert other.post("/api/auth/verify", json={"token": token}).status_code == 400
    assert key not in [u["id"] for u in admin.get("/api/admin/users").json()]
    saved = admin.get("/api/runs/" + run["id"]).json()
    assert saved["status"] == "CANCELED" and saved["email"] == account["email"]
    assert admin.get("/api/code/" + run["id"] + "/download").status_code == 200
    assert admin.delete("/api/admin/users/" + key).status_code == 404
    assert (
        admin.put(
            "/api/admin/users/" + key,
            json={"approved": True, "role": "participant", "env_limit": 1024},
        ).status_code
        == 404
    )
    assert (
        admin.post("/api/admin/users", json={"email": account["email"]}).status_code
        == 200
    )
    assert key in [u["id"] for u in admin.get("/api/admin/users").json()]
    assert alice.get("/api/me").status_code == 401
    assert (
        admin.delete(
            "/api/admin/users/" + admin.get("/api/me").json()["id"]
        ).status_code
        == 409
    )


def test_deletion_retains_gpu_allocation_until_worker_confirms_stop(setup, job):
    app, db, cfg, client = setup
    admin, alice = client("admin@example.org"), client("alice@example.org")
    worker, _ = enroll(app, admin, max_jobs=1)
    heartbeat(worker)
    run = alice.post("/api/runs", json=job).json()
    schedule(db)
    # Deleting an admitted run requests cancellation; it cannot free unknown GPU usage.
    with db.connect() as c:
        old = dict(c.execute("SELECT * FROM jobs WHERE id=?", (run["id"],)).fetchone())
    assert old["status"] == "STARTING"
    assert (
        admin.delete(
            "/api/admin/users/" + alice.get("/api/me").json()["id"]
        ).status_code
        == 200
    )
    with db.connect() as c:
        current = dict(
            c.execute("SELECT * FROM jobs WHERE id=?", (run["id"],)).fetchone()
        )
    assert current["status"] == "STARTING" and current["cancel"] == 1
    assert current["lease"] == old["lease"] and current["server_id"] == old["server_id"]


@pytest.mark.parametrize("value", [1025, 2049, 3000, True, 2048.5, "2048"])
def test_environment_limits_cannot_be_arbitrary_numbers(setup, job, value):
    app, db, cfg, client = setup
    admin = client("admin@example.org")
    alice = client("alice@example.org")
    key = alice.get("/api/me").json()["id"]
    assert (
        admin.post(
            "/api/admin/users", json={"email": "new@example.org", "env_limit": value}
        ).status_code
        == 422
    )
    assert (
        admin.post(
            "/api/admin/users/bulk",
            json={"emails": ["new@example.org"], "env_limit": value},
        ).status_code
        == 422
    )
    assert (
        admin.put(
            "/api/admin/users/" + key,
            json={"approved": True, "role": "participant", "env_limit": value},
        ).status_code
        == 422
    )
    assert alice.post("/api/runs", json={**job, "num_envs": value}).status_code == 422
    settings = admin.get("/api/admin/settings").json()
    assert (
        admin.put(
            "/api/admin/settings", json={**settings, "min_envs": value}
        ).status_code
        == 422
    )
    from hub.config import DEFAULT_SERVER

    assert (
        admin.post(
            "/api/admin/servers",
            json={"name": "bad-limit", "config": {**DEFAULT_SERVER, "max_envs": value}},
        ).status_code
        == 422
    )


def test_password_generation_login_reset_and_no_persisted_cleartext(setup):
    app, db, cfg, client = setup
    admin, alice = client("admin@example.org"), client("alice@example.org")
    key = alice.get("/api/me").json()["id"]
    endpoint = "/api/admin/users/" + key + "/password"
    assert alice.post(endpoint, json={"send_email": False}).status_code == 403
    result = admin.post(endpoint, json={"send_email": False}).json()
    assert result["delivery"] == "not_requested" and len(result["password"]) >= 24
    assert alice.get("/api/me").status_code == 401
    with db.connect() as c:
        stored = c.execute(
            "SELECT password_hash FROM users WHERE id=?", (key,)
        ).fetchone()[0]
        assert verify_password(result["password"], stored)
        assert result["password"] not in str(
            [tuple(r) for r in c.execute("SELECT * FROM audit")]
        )
    assert result["password"].encode() not in cfg.db.read_bytes()
    assert "password_hash" not in admin.get("/api/admin/users").text
    visitor = TestClient(app, headers={"X-Hub-Request": "1"})
    assert (
        visitor.post(
            "/api/auth/password",
            json={"email": result["email"], "password": result["password"]},
        ).json()["redirect"]
        == "/dashboard"
    )
    reset = admin.post(endpoint, json={"send_email": False}).json()
    assert visitor.get("/api/me").status_code == 401
    assert (
        visitor.post(
            "/api/auth/password",
            json={"email": result["email"], "password": result["password"]},
        ).status_code
        == 401
    )
    assert (
        visitor.post(
            "/api/auth/password",
            json={"email": reset["email"], "password": reset["password"]},
        ).status_code
        == 200
    )


def test_smtp_configuration_delivery_and_secrets_stay_private(setup, monkeypatch):
    app, db, cfg, client = setup
    admin, alice = client("admin@example.org"), client("alice@example.org")
    smtp = MagicMock()
    smtp.send_message.return_value = {}
    smtp.__enter__.return_value = smtp
    monkeypatch.setattr(smtplib, "SMTP", MagicMock(return_value=smtp))
    settings = {
        "host": "smtp.example.org",
        "port": 587,
        "security": "starttls",
        "sender": "hub@example.org",
        "username": "hub@example.org",
        "password": "private-app-password",
    }
    assert alice.put("/api/admin/email", json=settings).status_code == 403
    result = admin.put("/api/admin/email", json=settings)
    assert result.status_code == 200 and result.json()["configured"]
    assert "private-app-password" not in result.text
    assert (cfg.data / "smtp.json").stat().st_mode & 0o777 == 0o600
    smtp.starttls.assert_called()
    smtp.login.assert_called_with("hub@example.org", "private-app-password")
    key = alice.get("/api/me").json()["id"]
    issued = admin.post(
        "/api/admin/users/" + key + "/password", json={"send_email": True}
    ).json()
    assert issued["delivery"] == "sent"
    message = smtp.send_message.call_args.args[0]
    assert (
        message["To"] == "alice@example.org"
        and issued["password"] in message.get_content()
    )
    assert admin.get("/api/admin/users").json()[1]["credential_email_at"] is not None
    assert issued["password"].encode() not in cfg.db.read_bytes()
    assert "private-app-password" not in admin.get("/api/admin/email").text
    assert (
        admin.post("/api/admin/email/test").json()["recipient"] == "admin@example.org"
    )
    monkeypatch.setattr(smtplib, "SMTP", MagicMock(side_effect=OSError("unavailable")))
    assert (
        admin.put(
            "/api/admin/email", json={**settings, "host": "broken.example.org"}
        ).status_code
        == 502
    )
    assert (
        json.loads((cfg.data / "smtp.json").read_text())["host"] == "smtp.example.org"
    )
    failed = admin.post(
        "/api/admin/users/" + key + "/password", json={"send_email": True}
    ).json()
    assert failed["delivery"] == "failed"
    assert (
        next(u for u in admin.get("/api/admin/users").json() if u["id"] == key)[
            "credential_email_at"
        ]
        is None
    )


def test_development_mail_is_explicit_and_private(setup):
    app, db, cfg, client = setup
    admin, alice = client("admin@example.org"), client("alice@example.org")
    key = alice.get("/api/me").json()["id"]
    issued = admin.post(
        "/api/admin/users/" + key + "/password", json={"send_email": True}
    ).json()
    assert issued["delivery"] == "development"
    file = next((cfg.data / "mail").glob("*.json"))
    assert file.stat().st_mode & 0o777 == 0o600
    assert issued["password"] in json.loads(file.read_text())["content"]


def test_email_generated_password_does_not_reset_it_or_revoke_session(
    setup, monkeypatch
):
    app, db, cfg, client = setup
    admin, alice = client("admin@example.org"), client("alice@example.org")
    key = alice.get("/api/me").json()["id"]
    generated = admin.post(
        "/api/admin/users/" + key + "/password", json={"send_email": False}
    ).json()
    assert generated["user_id"] == key
    visitor = TestClient(app, headers={"X-Hub-Request": "1"})
    visitor.post(
        "/api/auth/password",
        json={"email": generated["email"], "password": generated["password"]},
    ).raise_for_status()
    with db.connect() as c:
        original_hash = c.execute(
            "SELECT password_hash FROM users WHERE id=?", (key,)
        ).fetchone()[0]
    sent = []
    monkeypatch.setattr(
        Mailer,
        "send",
        lambda self, email, subject, content: sent.append((email, content)) or "sent",
    )
    endpoint = "/api/admin/users/" + key + "/password/email"
    assert (
        visitor.post(endpoint, json={"password": generated["password"]}).status_code
        == 403
    )
    assert (
        admin.post(endpoint, json={"password": "not-the-current-password"}).status_code
        == 409
    )
    assert not sent
    response = admin.post(endpoint, json={"password": generated["password"]})
    assert response.json()["delivery"] == "sent" and "password" not in response.json()
    assert sent[0][0] == generated["email"] and generated["password"] in sent[0][1]
    assert visitor.get("/api/me").status_code == 200
    with db.connect() as c:
        assert (
            c.execute("SELECT password_hash FROM users WHERE id=?", (key,)).fetchone()[
                0
            ]
            == original_hash
        )
        assert generated["password"] not in str(
            [tuple(r) for r in c.execute("SELECT * FROM audit")]
        )
    assert (
        admin.post(
            endpoint,
            json={
                "password": generated["password"],
                "email": "someone-else@example.org",
            },
        ).status_code
        == 422
    )
    admin.post(
        "/api/admin/users/" + key + "/password", json={"send_email": False}
    ).raise_for_status()
    assert (
        admin.post(endpoint, json={"password": generated["password"]}).status_code
        == 409
    )


def test_email_failure_keeps_generated_password_usable(setup, monkeypatch):
    app, db, cfg, client = setup
    admin, alice = client("admin@example.org"), client("alice@example.org")
    key = alice.get("/api/me").json()["id"]
    generated = admin.post(
        "/api/admin/users/" + key + "/password", json={"send_email": False}
    ).json()

    def fail(*args, **kwargs):
        raise OSError("mail unavailable")

    monkeypatch.setattr(Mailer, "send", fail)
    assert (
        admin.post(
            "/api/admin/users/" + key + "/password/email",
            json={"password": generated["password"]},
        ).json()["delivery"]
        == "failed"
    )
    visitor = TestClient(app, headers={"X-Hub-Request": "1"})
    assert (
        visitor.post(
            "/api/auth/password",
            json={"email": generated["email"], "password": generated["password"]},
        ).status_code
        == 200
    )
