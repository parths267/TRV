"""Read-only Upstox option chain. Orders are not sent from this module."""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import logging
import struct
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from app.config import REPO_ROOT, get_settings

log = logging.getLogger("bazaar.upstox")
IST = timezone(timedelta(hours=5, minutes=30))
_AUTO_RETRY_SECONDS = 300
_AUTO: dict = {"attempted": 0.0, "error": ""}
_REJECTED: dict = {"token": None}

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
_TOKEN_PATH = REPO_ROOT / "data" / "upstox_token.json"


class UpstoxError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _request(
    url: str,
    *,
    data: bytes | None = None,
    token: str | None = None,
    form: bool = False,
    extra_headers: dict | None = None,
) -> dict:
    headers = {"Accept": "application/json", "User-Agent": _UA}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if form:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    headers.update(extra_headers or {})
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        if exc.code == 401 and token:
            _REJECTED["token"] = token
        raw = exc.read().decode(errors="replace")
        message = raw[:300]
        try:
            payload = json.loads(raw)
            errors = payload.get("errors") or []
            if errors and errors[0].get("message"):
                message = errors[0]["message"]
        except json.JSONDecodeError:
            pass
        raise UpstoxError(exc.code, message) from exc


def save_token(access_token: str, source: str = "oauth") -> None:
    _TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    _TOKEN_PATH.write_text(
        json.dumps({
            "access_token": access_token,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "source": source,
        }),
        encoding="utf-8",
    )


def _read_token_file() -> dict:
    try:
        payload = json.loads(_TOKEN_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def last_reset(now: datetime | None = None) -> datetime:
    """Most recent 03:30 IST, when Upstox expires every access token."""
    now = (now or datetime.now(timezone.utc)).astimezone(IST)
    reset = now.replace(hour=3, minute=30, second=0, microsecond=0)
    if now < reset:
        reset -= timedelta(days=1)
    return reset


def token_is_current(payload: dict, now: datetime | None = None) -> bool:
    if not payload.get("access_token") or payload.get("access_token") == _REJECTED["token"]:
        return False
    try:
        saved = datetime.fromisoformat(payload["saved_at"])
    except (KeyError, TypeError, ValueError):
        return False
    if saved.tzinfo is None:
        saved = saved.replace(tzinfo=timezone.utc)
    return saved >= last_reset(now)


def totp_code(secret: str, at: float | None = None, digits: int = 6, step: int = 30) -> str:
    """RFC 6238 TOTP with HMAC-SHA1, as used by authenticator apps."""
    cleaned = secret.replace(" ", "").upper()
    key = base64.b32decode(cleaned + "=" * (-len(cleaned) % 8))
    counter = int((time.time() if at is None else at) // step)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10 ** digits).zfill(digits)


def auto_login_configured() -> bool:
    settings = get_settings()
    return bool(settings.upstox_api_key.strip() and settings.upstox_pin.strip() and settings.upstox_totp_secret.strip())


def totp_login() -> str:
    """Issue a fresh access token from the account PIN and TOTP. The previous token is revoked by Upstox."""
    settings = get_settings()
    body = json.dumps({
        "totp": totp_code(settings.upstox_totp_secret),
        "pin": settings.upstox_pin.strip(),
    }).encode()
    payload = _request(
        "https://api.upstox.com/v2/totp-login/authorization/token",
        data=body,
        extra_headers={"Content-Type": "application/json", "x-api-key": settings.upstox_api_key.strip()},
    )
    token = payload.get("access_token") or (payload.get("data") or {}).get("access_token")
    if not token:
        raise UpstoxError(502, "Upstox did not return an access token")
    save_token(token, source="totp")
    _AUTO["error"] = ""
    return token


def _auto_login() -> str | None:
    if not auto_login_configured():
        return None
    now = time.time()
    if now - _AUTO["attempted"] < _AUTO_RETRY_SECONDS:
        return None
    _AUTO["attempted"] = now
    try:
        token = totp_login()
    except (UpstoxError, ValueError, binascii.Error) as exc:
        _AUTO["error"] = getattr(exc, "message", None) or type(exc).__name__
        log.warning("Upstox TOTP login failed: %s", _AUTO["error"])
        return None
    log.info("Upstox access token refreshed with TOTP")
    return token


def load_token() -> str | None:
    """A token valid for today. Logs in with TOTP when the stored one has expired and auto-login is set up."""
    payload = _read_token_file()
    if token_is_current(payload):
        return payload["access_token"]
    return _auto_login()


def token_info() -> dict:
    payload = _read_token_file()
    return {
        "current": token_is_current(payload),
        "saved_at": payload.get("saved_at"),
        "source": payload.get("source", "oauth" if payload else None),
        "auto_login": auto_login_configured(),
        "auto_login_error": _AUTO["error"] or None,
    }


def exchange_code(code: str) -> str:
    settings = get_settings()
    body = urllib.parse.urlencode(
        {
            "code": code,
            "client_id": settings.upstox_api_key.strip(),
            "client_secret": settings.upstox_api_secret.strip(),
            "redirect_uri": settings.upstox_redirect_uri.strip(),
            "grant_type": "authorization_code",
        }
    ).encode()
    payload = _request("https://api.upstox.com/v2/login/authorization/token", data=body, form=True)
    token = payload.get("access_token")
    if not token:
        raise UpstoxError(502, "Upstox did not return an access token")
    save_token(token)
    return token


def fetch_contracts(instrument_key: str) -> list[dict]:
    token = load_token()
    if not token:
        raise UpstoxError(401, "Upstox login is required before the option chain can be read")
    query = urllib.parse.urlencode({"instrument_key": instrument_key})
    payload = _request(f"https://api.upstox.com/v2/option/contract?{query}", token=token)
    rows = payload.get("data") or []
    if not isinstance(rows, list):
        raise UpstoxError(502, "Upstox option contract response had no rows")
    return rows


def fetch_chain(instrument_key: str, expiry: str = "current_week") -> dict:
    token = load_token()
    if not token:
        raise UpstoxError(401, "Upstox login is required before the option chain can be read")
    query = urllib.parse.urlencode({"instrument_key": instrument_key, "expiry_date": expiry})
    payload = _request(f"https://api.upstox.com/v2/option/chain?{query}", token=token)
    rows = payload.get("data") or []
    if not isinstance(rows, list):
        raise UpstoxError(502, "Upstox option chain response had no rows")
    return {"expiry": expiry, "instrument_key": instrument_key, "rows": rows}


def chain_summary(chain: dict) -> dict:
    rows = chain["rows"]
    spot = next((row.get("underlying_spot_price") for row in rows if row.get("underlying_spot_price")), None)
    priced = [row for row in rows if row.get("strike_price") is not None]
    atm = None
    if spot is not None and priced:
        atm = min(priced, key=lambda row: abs(float(row["strike_price"]) - float(spot)))
    call = (atm or {}).get("call_options") or {}
    put = (atm or {}).get("put_options") or {}
    call_market = call.get("market_data") or {}
    put_market = put.get("market_data") or {}
    return {
        "instrument_key": chain["instrument_key"],
        "expiry": (atm or {}).get("expiry") or chain["expiry"],
        "strikes": len(rows),
        "spot": spot,
        "atm_strike": None if atm is None else atm.get("strike_price"),
        "atm_call_ltp": call_market.get("ltp"),
        "atm_call_oi": call_market.get("oi"),
        "atm_put_ltp": put_market.get("ltp"),
        "atm_put_oi": put_market.get("oi"),
        "source": "upstox",
    }
