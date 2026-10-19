import base64
from datetime import datetime

from app.providers import upstox


def test_totp_matches_rfc6238_vector():
    secret = base64.b32encode(b"12345678901234567890").decode()
    assert upstox.totp_code(secret, at=59, digits=8) == "94287082"
    assert upstox.totp_code(secret, at=1111111109, digits=8) == "07081804"
    assert upstox.totp_code(secret.lower(), at=59) == "287082"


def test_token_expires_at_0330_ist():
    ist = upstox.IST
    payload = {"access_token": "t", "saved_at": datetime(2026, 10, 19, 8, 50, tzinfo=ist).isoformat()}
    assert upstox.token_is_current(payload, now=datetime(2026, 10, 19, 23, 0, tzinfo=ist))
    assert upstox.token_is_current(payload, now=datetime(2026, 10, 20, 3, 29, tzinfo=ist))
    assert not upstox.token_is_current(payload, now=datetime(2026, 10, 20, 3, 31, tzinfo=ist))
    late = {"access_token": "t", "saved_at": datetime(2026, 10, 20, 2, 0, tzinfo=ist).isoformat()}
    assert not upstox.token_is_current(late, now=datetime(2026, 10, 20, 9, 0, tzinfo=ist))


def test_rejected_token_is_not_current(monkeypatch):
    payload = {"access_token": "bad", "saved_at": datetime.now(upstox.IST).isoformat()}
    monkeypatch.setitem(upstox._REJECTED, "token", "bad")
    assert not upstox.token_is_current(payload)


def test_auto_login_is_throttled(monkeypatch):
    calls = []
    monkeypatch.setattr(upstox, "_read_token_file", lambda: {})
    monkeypatch.setattr(upstox, "auto_login_configured", lambda: True)
    monkeypatch.setattr(upstox, "totp_login", lambda: calls.append(1) or (_ for _ in ()).throw(upstox.UpstoxError(401, "bad totp")))
    monkeypatch.setitem(upstox._AUTO, "attempted", 0.0)
    assert upstox.load_token() is None
    assert upstox.load_token() is None
    assert len(calls) == 1
    assert upstox._AUTO["error"] == "bad totp"
