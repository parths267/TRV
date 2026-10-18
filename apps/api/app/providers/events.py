"""Corporate-event providers.

Buyer and seller names are copied only from fields the source actually returned.
A bulk-deal endpoint is never labeled as a block deal. An event without a source
URL is not marked verified.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-IN,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}

OFFICIAL = {
    "bulk": "https://www.nseindia.com/market-data/bulk-deal",
    "block": "https://www.nseindia.com/market-data/block-deal",
    "announcements": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
    "bse_deals": "https://www.bseindia.com/markets/equity/EQReports/BulknBlockDeals.aspx",
}

_HEALTH = {
    "provider": "nse_public_disclosures",
    "role": "bulk_block_announcements",
    "official": True,
    "last_success_at": None,
    "last_error_at": None,
    "last_error": None,
    "note": (
        "Uses the public NSE website JSON that the exchange site itself calls. "
        "NSE often blocks automated clients. Failures stay visible; nothing is invented."
    ),
}


def health() -> dict:
    return dict(_HEALTH)


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _first(row: dict, *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, "", "-"):
            return row[key]
    return None


def _map_deal(row: dict, category: str) -> dict | None:
    if not isinstance(row, dict):
        return None
    symbol = _first(row, "symbol", "sym", "SYMBOL")
    if not symbol:
        return None
    quantity = _num(_first(row, "quantityTraded", "qty", "QTOTBUY" , "quantity"))
    price = _num(_first(row, "tradePrice", "avgPrice", "watp", "price", "TP"))
    value = None if quantity is None or price is None else round(quantity * price, 2)
    client = _first(row, "clientName", "client", "name")
    side = _first(row, "buySell", "dealType", "BS")
    return {
        "symbol": str(symbol).upper(),
        "company": _first(row, "securityName", "nameOfSecurity", "companyName"),
        "category": category,
        "client_name": client,
        "side": None if side is None else str(side).upper(),
        "quantity": quantity,
        "price": price,
        "value": value,
        "exchange": "NSE",
        "published_at": _first(row, "date", "tradeDate", "BD_DT_DATE"),
        "source_url": OFFICIAL["bulk" if category == "bulk_deal" else "block"],
        "verification_status": "source_field_present" if client else "source_returned_row_without_client",
        "buyer": client if side and str(side).upper().startswith("B") else None,
        "seller": client if side and str(side).upper().startswith("S") else None,
    }


def _rows(payload: Any) -> list:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "bulk", "block", "deals"):
            if isinstance(payload.get(key), list):
                return payload[key]
    return []


async def _nse_get(client: httpx.AsyncClient, path: str) -> Any:
    response = await client.get(path)
    response.raise_for_status()
    return response.json()


async def fetch_nse_activity() -> dict:
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=5)
    fmt = "%d-%m-%Y"
    query = f"from={start.strftime(fmt)}&to={today.strftime(fmt)}"
    try:
        async with httpx.AsyncClient(headers=_HEADERS, timeout=12, follow_redirects=True) as client:
            home = await client.get("https://www.nseindia.com/")
            if home.status_code >= 400:
                raise RuntimeError(f"NSE homepage returned HTTP {home.status_code}")
            bulk_payload = await _nse_get(client, f"https://www.nseindia.com/api/historical/bulk-deals?{query}")
            block_payload = await _nse_get(client, f"https://www.nseindia.com/api/historical/block-deals?{query}")
            ann_payload = await _nse_get(
                client,
                "https://www.nseindia.com/api/corporate-announcements?index=equities"
                f"&from_date={start.strftime(fmt)}&to_date={today.strftime(fmt)}",
            )
        bulk = [row for row in (_map_deal(item, "bulk_deal") for item in _rows(bulk_payload)) if row]
        block = [row for row in (_map_deal(item, "block_deal") for item in _rows(block_payload)) if row]
        announcements = []
        for item in _rows(ann_payload):
            if not isinstance(item, dict):
                continue
            symbol = _first(item, "symbol", "sm_name")
            subject = _first(item, "subject", "desc", "attchmntText")
            if not symbol and not subject:
                continue
            announcements.append(
                {
                    "symbol": None if symbol is None else str(symbol).upper(),
                    "company": _first(item, "sm_name", "company"),
                    "category": "announcement",
                    "subject": subject,
                    "published_at": _first(item, "an_dt", "sort_date", "date"),
                    "source_url": _first(item, "attchmntFile", "attachment") or OFFICIAL["announcements"],
                    "verification_status": "source_field_present",
                    "exchange": "NSE",
                    "buyer": None,
                    "seller": None,
                }
            )
        _HEALTH["last_success_at"] = datetime.now(timezone.utc).isoformat()
        _HEALTH["last_error"] = None
        return {
            "status": "ok",
            "provider": "nse_public_disclosures",
            "data_mode": "live",
            "bulk_deals": bulk,
            "block_deals": block,
            "announcements": announcements,
            "official_pages": OFFICIAL,
            "window": {"from": start.isoformat(), "to": today.isoformat()},
        }
    except Exception as exc:
        _HEALTH["last_error_at"] = datetime.now(timezone.utc).isoformat()
        _HEALTH["last_error"] = str(exc)
        return {
            "status": "unavailable",
            "provider": "nse_public_disclosures",
            "data_mode": "live",
            "reason": str(exc),
            "bulk_deals": [],
            "block_deals": [],
            "announcements": [],
            "official_pages": OFFICIAL,
            "bse": {
                "status": "not_integrated",
                "official_url": OFFICIAL["bse_deals"],
                "reason": "BSE bulk and block pages are not parsed in this release.",
            },
        }
