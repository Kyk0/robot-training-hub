from dataclasses import replace

from fastapi.testclient import TestClient

from hub.app import create_app
from hub.cli import seed


def test_local_demo_accounts_sign_in_without_registration_and_keep_roles(setup):
    app, db, cfg, _ = setup
    seed(db, "admin@workshop.example", 18)
    for role, redirect in [("admin", "/admin"), ("participant", "/dashboard")]:
        client = TestClient(app, client=("127.0.0.1", 12345))
        client.headers["X-Hub-Request"] = "1"
        assert client.get("/api/health").json()["demo_login"]
        response = client.post("/api/auth/demo", json={"role": role})
        assert response.status_code == 200
        assert response.json()["redirect"] == redirect
        assert "HttpOnly" in response.headers["set-cookie"]
        assert client.get("/api/me").json()["role"] == role
        assert client.get("/api/me").status_code == 200
        assert client.get("/api/admin/users").status_code == (
            200 if role == "admin" else 403
        )
    assert client.post("/api/auth/demo", json={"role": "superuser"}).status_code == 422


def test_demo_shortcut_refused_in_production_and_nonlocal_requests(setup):
    app, db, cfg, _ = setup
    seed(db, "admin@workshop.example", 18)
    cases = [
        (app, "192.0.2.10"),
        (create_app(replace(cfg, development=False)), "127.0.0.1"),
        (create_app(replace(cfg, public_url="https://hub.example.edu")), "127.0.0.1"),
    ]
    for application, peer in cases:
        client = TestClient(application, client=(peer, 12345))
        client.headers["X-Hub-Request"] = "1"
        assert not client.get("/api/health").json()["demo_login"]
        assert client.post("/api/auth/demo", json={"role": "admin"}).status_code == 404


def test_localhost_alias_can_use_demo_but_external_origin_cannot(setup):
    app, db, cfg, _ = setup
    seed(db, "admin@workshop.example", 18)
    client = TestClient(
        app, base_url="http://localhost:8000", client=("127.0.0.1", 12345)
    )
    client.headers["X-Hub-Request"] = "1"
    assert (
        client.post(
            "/api/auth/demo",
            json={"role": "admin"},
            headers={"Origin": "http://localhost:8000"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/auth/demo",
            json={"role": "admin"},
            headers={"Origin": "https://evil.example"},
        ).status_code
        == 403
    )
