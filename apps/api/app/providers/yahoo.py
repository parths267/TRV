"""Yahoo Finance adapter.

This is an unofficial chart endpoint already used by tradingview-mcp. It is not an
NSE or BSE feed. India quotes from this source are delayed, can be missing, and
must not be redistributed as a commercial market-data product without a license.
"""
from __future__ import annotations

import json
import time
import urllib.request
from datetime import datetime, timezone
from typing import Any

from tradingview_mcp.core.services.backtest_service import _fetch_ohlcv
from tradingview_mcp.core.services.yahoo_finance_service import _fetch_quote, _format_quote, _valid_closes
from tradingview_mcp.core.utils.yahoo_symbols import encode_yahoo_symbol

_CACHE: dict[str, tuple[float, Any]] = {}
_HEALTH = {
    "provider": "yahoo_finance",
    "role": "quotes_and_ohlcv",
    "official": False,
    "delayed": True,
    "last_success_at": None,
    "last_error_at": None,
    "last_error": None,
    "successes": 0,
    "failures": 0,
    "licensing": (
        "Unofficial Yahoo Finance chart API. Confirm terms before commercial redistribution. "
        "Not a substitute for an NSE or BSE market-data license."
    ),
}

_INTERVALS = {
    "1m": ("1m", "1d"),
    "5m": ("5m", "5d"),
    "15m": ("15m", "5d"),
    "30m": ("30m", "1mo"),
    "1h": ("1h", "1mo"),
    "1d": ("1d", "2y"),
    "1w": ("1wk", "5y"),
}

_UA = "bazaar-intelligence/0.1 research"


def health() -> dict:
    return dict(_HEALTH)


def _remember(ok: bool, error: str | None = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    if ok:
        _HEALTH["last_success_at"] = now
        _HEALTH["successes"] += 1
        _HEALTH["last_error"] = None
    else:
        _HEALTH["last_error_at"] = now
        _HEALTH["last_error"] = error
        _HEALTH["failures"] += 1


def _cache_get(key: str, ttl: float) -> Any | None:
    hit = _CACHE.get(key)
    if not hit:
        return None
    if time.time() - hit[0] > ttl:
        return None
    return hit[1]


def _cache_set(key: str, value: Any) -> Any:
    _CACHE[key] = (time.time(), value)
    return value


def _iso(ts: int | None) -> str | None:
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def get_quote(yahoo_symbol: str) -> dict:
    cached = _cache_get(f"q:{yahoo_symbol}", 15)
    if cached:
        return cached
    try:
        raw = _fetch_quote(yahoo_symbol)
        quote = _format_quote(yahoo_symbol, raw)
        meta = raw.get("meta") or {}
        quote["market_time"] = _iso(meta.get("regularMarketTime"))
        quote["exchange_timezone"] = meta.get("exchangeTimezoneName")
        quote["sparkline"] = [round(float(close), 2) for close in _valid_closes(raw)[-12:]]
        quote["provider"] = "yahoo_finance"
        quote["delayed"] = True
        quote["official_exchange_feed"] = False
        if quote.get("price") is None and "error" not in quote:
            quote["error"] = "Quote returned no price."
        if "error" in quote:
            _remember(False, quote["error"])
        else:
            _remember(True)
        return _cache_set(f"q:{yahoo_symbol}", quote)
    except Exception as exc:
        _remember(False, str(exc))
        return {
            "symbol": yahoo_symbol,
            "error": str(exc),
            "provider": "yahoo_finance",
            "delayed": True,
            "official_exchange_feed": False,
        }


def _parse_chart(payload: dict, interval: str) -> list[dict]:
    result = payload["chart"]["result"][0]
    timestamps = result.get("timestamp") or []
    quote = result["indicators"]["quote"][0]
    date_fmt = "%Y-%m-%d" if interval in {"1d", "1w"} else "%Y-%m-%d %H:%M"
    candles = []
    for i, ts in enumerate(timestamps):
        o, h, l, c = quote["open"][i], quote["high"][i], quote["low"][i], quote["close"][i]
        v = quote["volume"][i] if quote.get("volume") else None
        if None in (o, h, l, c):
            continue
        candles.append(
            {
                "date": datetime.fromtimestamp(ts, tz=timezone.utc).strftime(date_fmt),
                "open": round(o, 4),
                "high": round(h, 4),
                "low": round(l, 4),
                "close": round(c, 4),
                "volume": v or 0,
            }
        )
    return candles


def get_candles(yahoo_symbol: str, interval: str) -> dict:
    if interval not in _INTERVALS:
        return {
            "error": f"Interval '{interval}' is not offered. Choose: {', '.join(_INTERVALS)}.",
            "candles": [],
            "provider": "yahoo_finance",
        }
    cached = _cache_get(f"c:{yahoo_symbol}:{interval}", 300 if interval in {"1d", "1w"} else 60)
    if cached:
        return cached
    yf_interval, yf_range = _INTERVALS[interval]
    try:
        if interval == "1d":
            candles = _fetch_ohlcv(yahoo_symbol, "2y", "1d")
            adjusted = True
        elif interval == "1h":
            candles = _fetch_ohlcv(yahoo_symbol, "1mo", "1h")
            adjusted = False
        else:
            url = (
                "https://query1.finance.yahoo.com/v8/finance/chart/"
                f"{encode_yahoo_symbol(yahoo_symbol)}?interval={yf_interval}&range={yf_range}"
            )
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=15) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            candles = _parse_chart(payload, interval)
            adjusted = False
        _remember(True)
        body = {
            "symbol": yahoo_symbol,
            "interval": interval,
            "candles": candles,
            "count": len(candles),
            "provider": "yahoo_finance",
            "adjusted": adjusted,
            "delayed": True,
            "official_exchange_feed": False,
            "range_requested": yf_range,
            "empty": len(candles) == 0,
        }
        return _cache_set(f"c:{yahoo_symbol}:{interval}", body)
    except Exception as exc:
        _remember(False, str(exc))
        return {
            "symbol": yahoo_symbol,
            "interval": interval,
            "candles": [],
            "count": 0,
            "error": str(exc),
            "provider": "yahoo_finance",
            "delayed": True,
            "official_exchange_feed": False,
            "empty": True,
        }
