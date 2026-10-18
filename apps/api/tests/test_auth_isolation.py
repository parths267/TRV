def _register(client, email: str):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "a-long-password", "name": email},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body


def test_users_cannot_read_each_others_watchlists(client):
    headers_a, _ = _register(client, "a@example.com")
    headers_b, _ = _register(client, "b@example.com")
    created = client.post("/api/v1/watchlists", json={"name": "Private"}, headers=headers_a)
    assert created.status_code == 200, created.text
    watchlist_id = created.json()["id"]
    added = client.post(
        f"/api/v1/watchlists/{watchlist_id}/symbols",
        json={"symbol": "RELIANCE", "exchange": "NSE"},
        headers=headers_a,
    )
    assert added.status_code == 200
    assert added.json()["items"][0]["symbol"] == "RELIANCE"

    foreign = client.get("/api/v1/watchlists", headers=headers_b)
    assert foreign.status_code == 200
    assert foreign.json()["watchlists"] == []
    missing = client.delete(f"/api/v1/watchlists/{watchlist_id}", headers=headers_b)
    assert missing.status_code == 404


def test_free_plan_cannot_backtest_or_use_assistant(client):
    headers, _ = _register(client, "free@example.com")
    backtest = client.post(
        "/api/v1/strategies/backtest",
        json={"symbol": "RELIANCE", "strategy": "donchian"},
        headers=headers,
    )
    assert backtest.status_code == 402
    ask = client.post("/api/v1/assistant/ask", json={"question": "Any breakouts today?"}, headers=headers)
    assert ask.status_code == 402


def test_email_verification_round_trip(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "verify@example.com", "password": "a-long-password", "name": "V"},
    )
    token = response.json()["verification_token"]
    verified = client.post("/api/v1/auth/verify-email", json={"token": token})
    assert verified.status_code == 200
    me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {response.json()['access_token']}"},
    )
    assert me.json()["email_verified"] is True
