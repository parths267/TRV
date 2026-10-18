"""Read-only Upstox option chain. Orders are not sent from this module."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from app.config import REPO_ROOT, get_settings

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


def _request(url: str, *, data: bytes | None = None, token: str | None = None, form: bool = False) -> dict:
    headers = {"Accept": "application/json", "User-Agent": _UA}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if form:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
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


def save_token(access_token: str) -> None:
    _TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    _TOKEN_PATH.write_text(
        json.dumps({"access_token": access_token, "saved_at": datetime.now(timezone.utc).isoformat()}),
        encoding="utf-8",
    )


def load_token() -> str | None:
    try:
        payload = json.loads(_TOKEN_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    token = payload.get("access_token") if isinstance(payload, dict) else None
    return token or None


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
