"""Explicit demo fixtures. These numbers are synthetic and must never be shown as live quotes."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.market.universe import INDICES, NIFTY_50


def _series(symbol: str, n: int = 260, interval_days: int = 1) -> list[dict]:
    seed = sum(ord(ch) for ch in symbol) or 1
    price = 80 + (seed % 2400)
    start = datetime.now(timezone.utc) - timedelta(days=n * interval_days)
    candles = []
    for i in range(n):
        step = ((seed * (i + 3)) % 17) - 8
        # A few symbols are shaped into a closing breakout so the scanner can be demonstrated.
        if symbol.startswith("REL") and i == n - 1:
            step = 40
        open_ = price
        close = max(1.0, price + step)
        high = max(open_, close) + ((seed + i) % 4)
        low = max(0.5, min(open_, close) - ((seed + i) % 3))
        volume = 200_000 + ((seed * (i + 11)) % 2_000_000)
        if symbol.startswith("REL") and i == n - 1:
            volume = volume * 4
            high = close
        candles.append(
            {
                "date": (start + timedelta(days=i * interval_days)).strftime("%Y-%m-%d"),
                "open": round(open_, 4),
                "high": round(high, 4),
                "low": round(low, 4),
                "close": round(close, 4),
                "volume": volume,
            }
        )
        price = close
    return candles


def quote_from_candles(symbol: str, candles: list[dict]) -> dict:
    last = candles[-1]
    prev = candles[-2]["close"]
    price = last["close"]
    return {
        "symbol": symbol,
        "price": price,
        "previous_close": prev,
        "change": round(price - prev, 4),
        "change_pct": round((price - prev) / prev * 100, 2),
        "currency": "INR",
        "exchange": "DEMO",
        "market_state": "DEMO",
        "52w_high": max(c["high"] for c in candles[-252:]),
        "52w_low": min(c["low"] for c in candles[-252:]),
        "price_source": "demo_fixture",
        "quote_stale": False,
        "market_time": last["date"],
        "sparkline": [round(candle["close"], 2) for candle in candles[-12:]],
        "provider": "demo",
        "delayed": False,
        "official_exchange_feed": False,
        "data_mode": "demo",
    }


def get_quote(yahoo_symbol: str) -> dict:
    candles = _series(yahoo_symbol)
    return quote_from_candles(yahoo_symbol, candles)


def get_candles(yahoo_symbol: str, interval: str) -> dict:
    if interval not in {"1m", "5m", "15m", "30m", "1h", "1d", "1w"}:
        return {"error": "Unsupported interval", "candles": [], "provider": "demo", "data_mode": "demo"}
    candles = _series(yahoo_symbol, n=80 if interval != "1d" else 260)
    return {
        "symbol": yahoo_symbol,
        "interval": interval,
        "candles": candles,
        "count": len(candles),
        "provider": "demo",
        "adjusted": False,
        "delayed": False,
        "official_exchange_feed": False,
        "data_mode": "demo",
        "empty": False,
        "note": "Synthetic candles for demonstration. Not market prices.",
    }


def demo_events() -> dict:
    return {
        "status": "demo",
        "provider": "demo",
        "data_mode": "demo",
        "note": "Fixture events for layout only. Not exchange disclosures.",
        "bulk_deals": [
            {
                "symbol": "DEMO",
                "company": "Demo Industries",
                "category": "bulk_deal",
                "client_name": "Demo Buyer LLP",
                "side": "BUY",
                "quantity": 100000,
                "price": 100.0,
                "value": 10000000,
                "exchange": "NSE",
                "published_at": "2026-01-01",
                "source_url": "https://www.nseindia.com/market-data/bulk-deal",
                "verification_status": "demo_fixture",
            }
        ],
        "block_deals": [
            {
                "symbol": "DEMO",
                "company": "Demo Industries",
                "category": "block_deal",
                "client_name": "Demo Seller Fund",
                "side": "SELL",
                "quantity": 250000,
                "price": 99.5,
                "value": 24875000,
                "exchange": "NSE",
                "published_at": "2026-01-01",
                "source_url": "https://www.nseindia.com/market-data/block-deal",
                "verification_status": "demo_fixture",
            }
        ],
        "announcements": [
            {
                "symbol": "DEMO",
                "company": "Demo Industries",
                "category": "announcement",
                "subject": "Demo result announcement",
                "published_at": "2026-01-01",
                "source_url": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
                "verification_status": "demo_fixture",
                "buyer": None,
                "seller": None,
            }
        ],
    }


def health() -> dict:
    return {
        "provider": "demo",
        "role": "explicit_demo_mode",
        "official": False,
        "delayed": False,
        "symbols": len(NIFTY_50),
        "indices": len(INDICES),
        "note": "DATA_MODE=demo. None of these records are live market data.",
    }
