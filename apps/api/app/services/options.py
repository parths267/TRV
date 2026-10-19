"""Option chains from the signed-in Upstox account. Premiums are not invented."""
from __future__ import annotations

import re
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from app.market.session import IST, session_status
from app.providers.upstox import UpstoxError, fetch_chain, fetch_contracts

# id, display name, Upstox instrument key, trading-symbol prefix.
# Midcap 100 and Smallcap 100 are not the same as Nifty Midcap Select.
UNDERLYINGS: dict[str, tuple[str, str | None, str | None]] = {
    "nifty50": ("NIFTY 50", "NSE_INDEX|Nifty 50", "NIFTY"),
    "banknifty": ("NIFTY Bank", "NSE_INDEX|Nifty Bank", "BANKNIFTY"),
    "niftyfin": ("NIFTY Financial Services", "NSE_INDEX|Nifty Fin Service", "FINNIFTY"),
    "sensex": ("BSE Sensex", "BSE_INDEX|SENSEX", "SENSEX"),
    "niftyit": ("NIFTY IT", "NSE_INDEX|Nifty IT", None),
    "niftymid": ("NIFTY Midcap 100", None, None),
    "niftysmall": ("NIFTY Smallcap 100", None, None),
}

_CONTRACT_TTL = 60 * 60
_CHAIN_TTL = 20
_APP_LOT_CAP = 20
_LOCK = threading.Lock()
_CONTRACTS: dict[str, tuple[float, dict]] = {}
_CHAINS: dict[tuple[str, str], tuple[float, dict]] = {}
_MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}
_SYMBOL = re.compile(
    r"^(BANKNIFTY|FINNIFTY|SENSEX|NIFTY) (\d+(?:\.\d+)?) (CE|PE) (\d{1,2}) ([A-Z]{3}) (\d{2})$"
)
_PREFIX_INDEX = {"NIFTY": "nifty50", "BANKNIFTY": "banknifty", "FINNIFTY": "niftyfin", "SENSEX": "sensex"}


def catalog() -> list[dict]:
    return [
        {"id": key, "name": name, "has_chain": instrument is not None}
        for key, (name, instrument, _prefix) in UNDERLYINGS.items()
    ]


def build_chain(index_id: str, expiry: str | None = None) -> dict:
    spec = UNDERLYINGS.get(index_id)
    if spec is None:
        raise HTTPException(status_code=404, detail="Unknown index")
    name, instrument, _prefix = spec
    base = {
        "index": index_id,
        "name": name,
        "indexes": catalog(),
        "session": session_status(),
        "source": "upstox",
        "live_trading_enabled": False,
    }
    if instrument is None:
        return {
            **base,
            "available": False,
            "reason": (
                f"{name} has no index option chain on Upstox. "
                "A different index is not substituted in its place."
            ),
            "spot": None,
            "expiry": None,
            "expiries": [],
            "lot_size": None,
            "freeze_quantity": None,
            "max_lots": None,
            "rows": [],
            "as_of": None,
        }
    contracts = _contracts(instrument)
    expiries = contracts["expiries"]
    if not expiries:
        return {
            **base,
            "available": False,
            "reason": f"Upstox lists no option contracts for {name}.",
            "spot": None,
            "expiry": None,
            "expiries": [],
            "lot_size": None,
            "freeze_quantity": None,
            "max_lots": None,
            "rows": [],
            "as_of": None,
        }
    chosen = _choose_expiry(expiries, expiry)
    cached = _read(_CHAINS, (instrument, chosen), _CHAIN_TTL)
    if cached and cached.get("contracts_at") == contracts["fetched_at"]:
        return {**base, **cached["body"]}
    raw = fetch_chain(instrument, chosen)
    body = _normalize(contracts, chosen, raw.get("rows") or [])
    _write(_CHAINS, (instrument, chosen), {"contracts_at": contracts["fetched_at"], "body": body})
    return {**base, **body}


def quote_contract(index_id: str, expiry: str, strike: float, right: str) -> dict:
    right = right.upper().strip()
    if right not in {"CE", "PE"}:
        raise HTTPException(status_code=400, detail="right must be CE or PE")
    chain = build_chain(index_id, expiry)
    if not chain["available"]:
        raise HTTPException(status_code=409, detail=chain["reason"])
    for row in chain["rows"]:
        if abs(float(row["strike"]) - float(strike)) > 0.01:
            continue
        leg = row["call"] if right == "CE" else row["put"]
        if not leg or leg.get("ltp") is None or leg["ltp"] <= 0:
            raise HTTPException(
                status_code=409,
                detail="That contract has no premium in the Upstox chain. The paper order was not filled.",
            )
        if not leg.get("trading_symbol"):
            raise HTTPException(
                status_code=409,
                detail="That contract has no trading symbol in the Upstox contract list. The paper order was not filled.",
            )
        if not chain.get("lot_size"):
            raise HTTPException(
                status_code=409,
                detail="Lot size was not in the Upstox contract list. The paper order was not filled.",
            )
        return {
            "trading_symbol": leg["trading_symbol"],
            "ltp": float(leg["ltp"]),
            "lot_size": int(chain["lot_size"]),
            "max_lots": chain.get("max_lots"),
            "expiry": chain["expiry"],
            "as_of": chain.get("as_of"),
            "quote_stale": chain["session"]["state"] != "regular",
        }
    raise HTTPException(status_code=404, detail="That strike is not in this expiry.")


def option_mark(symbol: str) -> tuple[float | None, str | None]:
    parsed = parse_trading_symbol(symbol)
    if parsed is None:
        return None, None
    try:
        chain = build_chain(parsed["index"], parsed["expiry"])
    except UpstoxError:
        return None, None
    if not chain.get("available"):
        return None, None
    side = "call" if parsed["right"] == "CE" else "put"
    for row in chain["rows"]:
        if abs(float(row["strike"]) - parsed["strike"]) > 0.01:
            continue
        leg = row.get(side) or {}
        price = leg.get("ltp")
        if price is None or price <= 0:
            return None, chain.get("as_of")
        return float(price), chain.get("as_of")
    return None, None


def parse_trading_symbol(symbol: str) -> dict | None:
    match = _SYMBOL.match(symbol.strip().upper())
    if match is None:
        return None
    prefix, strike, right, day, month, year = match.groups()
    month_no = _MONTHS.get(month)
    if month_no is None:
        return None
    return {
        "index": _PREFIX_INDEX[prefix],
        "strike": float(strike),
        "right": right,
        "expiry": f"{2000 + int(year):04d}-{month_no:02d}-{int(day):02d}",
    }


def _contracts(instrument: str) -> dict:
    cached = _read(_CONTRACTS, instrument, _CONTRACT_TTL)
    if cached:
        return cached
    rows = fetch_contracts(instrument)
    by_key = {}
    expiries: set[str] = set()
    for row in rows:
        expiry = str(row.get("expiry") or "")[:10]
        if expiry:
            expiries.add(expiry)
        key = row.get("instrument_key")
        if key:
            by_key[key] = {
                "trading_symbol": row.get("trading_symbol") or "",
                "lot_size": _num(row.get("lot_size")),
                "freeze_quantity": _num(row.get("freeze_quantity")),
                "expiry": expiry,
            }
    payload = {
        "fetched_at": time.time(),
        "expiries": sorted(expiries),
        "by_key": by_key,
    }
    _write(_CONTRACTS, instrument, payload)
    return payload


def _choose_expiry(expiries: list[str], requested: str | None) -> str:
    if requested:
        if requested not in expiries:
            raise HTTPException(status_code=400, detail="That expiry is not in the Upstox contract list.")
        return requested
    today = datetime.now(IST).date().isoformat()
    upcoming = [item for item in expiries if item >= today]
    if not upcoming:
        return expiries[-1]
    # After the close on expiry day the nearest contract is already settled.
    # Open the next listed expiry, and keep today in the dropdown.
    if session_status()["state"] != "regular" and upcoming[0] == today and len(upcoming) > 1:
        return upcoming[1]
    return upcoming[0]


def _normalize(contracts: dict, expiry: str, rows: list) -> dict:
    by_key = contracts["by_key"]
    sample = next((item for item in by_key.values() if item["expiry"] == expiry), None)
    lot_size = None if sample is None else sample.get("lot_size")
    freeze = None if sample is None else sample.get("freeze_quantity")
    max_lots = _APP_LOT_CAP
    max_note = "Paper orders are capped at 20 lots because this feed did not include a freeze quantity."
    if lot_size and freeze and freeze >= lot_size:
        max_lots = int(freeze // lot_size)
        max_note = "Maximum lots follow the Upstox freeze quantity for this contract."
    spot = None
    normalized = []
    for row in rows:
        strike = _num(row.get("strike_price"))
        if strike is None:
            continue
        if spot is None:
            spot = _num(row.get("underlying_spot_price"))
        normalized.append(
            {
                "strike": strike,
                "call": _leg(row.get("call_options") or {}, by_key),
                "put": _leg(row.get("put_options") or {}, by_key),
            }
        )
    normalized.sort(key=lambda item: item["strike"])
    return {
        "available": True,
        "reason": None,
        "spot": spot,
        "expiry": expiry,
        "expiries": contracts["expiries"],
        "lot_size": None if lot_size is None else int(lot_size),
        "freeze_quantity": freeze,
        "max_lots": max_lots,
        "max_lots_note": max_note,
        "rows": normalized,
        "as_of": datetime.now(ZoneInfo("UTC")).isoformat(),
    }


def _leg(raw: dict, by_key: dict) -> dict | None:
    if not raw:
        return None
    market = raw.get("market_data") or {}
    greeks = raw.get("option_greeks") or {}
    key = raw.get("instrument_key")
    known = by_key.get(key) or {}
    return {
        "instrument_key": key,
        "trading_symbol": known.get("trading_symbol") or None,
        "ltp": _num(market.get("ltp")),
        "close": _num(market.get("close_price")),
        "oi": _num(market.get("oi")),
        "prev_oi": _num(market.get("prev_oi")),
        "iv": _num(greeks.get("iv")),
        "delta": _num(greeks.get("delta")),
        "theta": _num(greeks.get("theta")),
        "gamma": _num(greeks.get("gamma")),
    }


def _num(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _read(store: dict, key, ttl: float):
    with _LOCK:
        hit = store.get(key)
    if hit and time.time() - hit[0] <= ttl:
        return hit[1]
    return None


def _write(store: dict, key, value) -> None:
    with _LOCK:
        store[key] = (time.time(), value)
