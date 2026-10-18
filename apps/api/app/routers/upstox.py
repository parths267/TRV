"""Upstox login and a read-only option chain check."""
from __future__ import annotations

import html
import logging
import secrets
import time
import urllib.parse

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse

from app.config import get_settings
from app.providers.upstox import UpstoxError, chain_summary, exchange_code, fetch_chain, load_token

log = logging.getLogger("bazaar.upstox")
router = APIRouter(prefix="/api/v1/upstox", tags=["upstox"])
_PENDING_STATE: dict[str, float] = {}
_NIFTY = "NSE_INDEX|Nifty 50"


def _credentials() -> tuple[str, str, str]:
    settings = get_settings()
    key = settings.upstox_api_key.strip()
    secret = settings.upstox_api_secret.strip()
    redirect_uri = settings.upstox_redirect_uri.strip()
    if not key or not secret:
        raise HTTPException(status_code=400, detail="UPSTOX_API_KEY and UPSTOX_API_SECRET are missing")
    return key, secret, redirect_uri


def _page(title: str, body: str) -> HTMLResponse:
    safe_title = html.escape(title)
    document = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{safe_title}</title>
<style>
body {{ font-family: Segoe UI, sans-serif; background: #f5f7f8; color: #1b2522; margin: 0; }}
main {{ max-width: 640px; margin: 48px auto; background: #fff; padding: 28px; border-radius: 12px; }}
a {{ color: #00b386; }}
</style></head>
<body><main><h1>{safe_title}</h1>{body}</main></body></html>"""
    return HTMLResponse(document)


@router.get("/login")
def login():
    key, _secret, redirect_uri = _credentials()
    now = time.time()
    stale = [item for item, stamp in _PENDING_STATE.items() if now - stamp > 600]
    for item in stale:
        _PENDING_STATE.pop(item, None)
    state = secrets.token_urlsafe(16)
    _PENDING_STATE[state] = now
    query = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": key,
            "redirect_uri": redirect_uri,
            "state": state,
        }
    )
    return RedirectResponse(f"https://api.upstox.com/v2/login/authorization/dialog?{query}")


@router.get("/callback")
def callback(code: str = Query(default=""), state: str = Query(default=""), error: str = Query(default="")):
    if error:
        return _page("Upstox login declined", f"<p>{html.escape(error)}</p><p><a href=\"/api/v1/upstox/login\">Try again</a></p>")
    if not code or state not in _PENDING_STATE:
        return _page(
            "Login did not finish",
            "<p>That login link was already used or it expired.</p>"
            "<p>Sign in with your mobile number and OTP. The QR code login does not work for this connection.</p>"
            "<p><a href=\"/api/v1/upstox/login\">Try again</a></p>",
        )
    _PENDING_STATE.pop(state, None)
    try:
        exchange_code(code)
        summary = chain_summary(fetch_chain(_NIFTY, "current_week"))
    except UpstoxError as exc:
        log.warning("Upstox login failed: %s", exc.message)
        return _page(
            "Upstox rejected the login",
            f"<p>{html.escape(exc.message)}</p>"
            "<p>The login code works only once. Open the link again and sign in with your mobile number and OTP, not the QR code.</p>"
            "<p><a href=\"/api/v1/upstox/login\">Try again</a></p>",
        )
    rows = "".join(
        f"<tr><td>{html.escape(str(label))}</td><td>{html.escape(str(summary.get(key)))}</td></tr>"
        for label, key in (
            ("Expiry", "expiry"),
            ("Strikes", "strikes"),
            ("Spot", "spot"),
            ("ATM strike", "atm_strike"),
            ("ATM call", "atm_call_ltp"),
            ("ATM put", "atm_put_ltp"),
        )
    )
    return _page("Nifty option chain", f"<table>{rows}</table><p>Source: Upstox.</p>")


@router.get("/chain")
def chain(expiry: str = Query(default="current_week")):
    if not load_token():
        raise HTTPException(status_code=401, detail="Log in at /api/v1/upstox/login first")
    try:
        summary = chain_summary(fetch_chain(_NIFTY, expiry))
    except UpstoxError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message) from exc
    return {"ok": True, "chain": summary}
