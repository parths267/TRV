def test_health_sends_safe_headers(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-store"


def test_option_chain_check_requires_a_session(client):
    assert client.get("/api/v1/upstox/chain").status_code == 401
    assert client.get("/api/v1/market/status").status_code == 401


def test_production_closes_registration(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "app_env", "production")
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "new@example.com", "password": "a-long-password", "name": "N"},
    )
    assert response.status_code == 403


def test_repeated_sign_in_failures_pause(client):
    from app.routers.auth import _LOGIN_FAILS

    _LOGIN_FAILS.clear()
    for _ in range(8):
        failed = client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "wrong-password"})
        assert failed.status_code == 401
    locked = client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "wrong-password"})
    assert locked.status_code == 429
    _LOGIN_FAILS.clear()


def test_oversized_password_is_rejected(client):
    response = client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "x" * 129})
    assert response.status_code == 422
