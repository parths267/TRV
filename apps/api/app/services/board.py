"""Shared quote board for the dashboard, breadth, and heatmaps."""
from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from app.config import REPO_ROOT
from app.market.analysis import breadth
from app.market.universe import BANKING_WATCH, BY_SYMBOL, INDICES, NIFTY_50
from app.providers.registry import quotes

_CACHE: dict[str, tuple[float, dict]] = {}
_STALE_SECONDS = 20
_DISK = REPO_ROOT / "data" / "board_cache.json"
_REFRESH_LOCK = threading.Lock()


def _fetch_many(pairs: list[tuple[str, str]]) -> list[dict]:
    provider = quotes()

    def one(item: tuple[str, str]) -> dict:
        symbol, yahoo = item
        quote = provider.get_quote(yahoo)
        quote["display_symbol"] = symbol
        known = BY_SYMBOL.get(symbol)
        if known:
            quote["company"] = known.name
            quote["sector"] = known.sector
        return quote

    with ThreadPoolExecutor(max_workers=16) as pool:
        return list(pool.map(one, pairs))


def _read_disk() -> dict | None:
    try:
        payload = json.loads(_DISK.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) and payload.get("gainers") is not None else None


def _write_disk(payload: dict) -> None:
    try:
        _DISK.parent.mkdir(parents=True, exist_ok=True)
        _DISK.write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        return


def _remember(payload: dict) -> dict:
    _CACHE["nifty50"] = (time.time(), payload)
    _write_disk(payload)
    return payload


def _cached_board() -> dict | None:
    hit = _CACHE.get("nifty50")
    if hit:
        return hit[1]
    payload = _read_disk()
    if payload:
        _CACHE["nifty50"] = (time.time() - _STALE_SECONDS - 1, payload)
    return payload


def _build_board() -> dict:
    rows = _fetch_many([(item.symbol, item.yahoo) for item in NIFTY_50])
    ok = [row for row in rows if not row.get("error") and row.get("price") is not None]
    failed = [row for row in rows if row not in ok]
    changes = [row.get("change_pct") for row in ok]
    sectors: dict[str, list[float]] = {}
    for row in ok:
        if row.get("change_pct") is None:
            continue
        sectors.setdefault(row.get("sector") or "Unclassified", []).append(row["change_pct"])
    heatmap = [
        {
            "sector": name,
            "change_pct": round(sum(values) / len(values), 2),
            "count": len(values),
        }
        for name, values in sorted(sectors.items())
    ]
    ranked = sorted(
        [row for row in ok if row.get("change_pct") is not None],
        key=lambda row: row["change_pct"],
        reverse=True,
    )
    approaching = []
    for row in ok:
        high = row.get("52w_high")
        low = row.get("52w_low")
        price = row.get("price")
        if not price or not high or not low or high <= 0 or low <= 0:
            continue
        dist_high = (high - price) / high * 100
        dist_low = (price - low) / low * 100
        if dist_high <= 2 or dist_low <= 2:
            approaching.append(
                {
                    "symbol": row["display_symbol"],
                    "company": row.get("company"),
                    "price": price,
                    "distance_from_high_pct": round(dist_high, 2),
                    "distance_from_low_pct": round(dist_low, 2),
                    "method": "Yahoo fiftyTwoWeekHigh/Low versus the latest price. Not the 252-session recalculation.",
                }
            )
    payload = {
        "quotes": ok,
        "failures": [
            {"symbol": row.get("display_symbol"), "error": row.get("error", "missing price")} for row in failed
        ],
        "breadth": breadth(changes),
        "heatmap": heatmap,
        "gainers": ranked[:5],
        "losers": list(reversed(ranked[-5:])) if ranked else [],
        "approaching_52w_provider": approaching[:8],
        "universe": "nifty50_snapshot",
        "indices": _index_rows(),
    }
    return _remember(payload)


def _refresh_async() -> None:
    if not _REFRESH_LOCK.acquire(blocking=False):
        return

    def run() -> None:
        try:
            _build_board()
        finally:
            _REFRESH_LOCK.release()

    threading.Thread(target=run, daemon=True).start()


def prime_board() -> None:
    """Serve the last saved board immediately, then refresh it off the request path."""
    _cached_board()
    _refresh_async()


def universe_board() -> dict:
    cached = _cached_board()
    fresh = _CACHE.get("nifty50")
    if cached and fresh and time.time() - fresh[0] <= _STALE_SECONDS:
        return cached
    if cached:
        _refresh_async()
        return cached
    with _REFRESH_LOCK:
        cached = _cached_board()
        fresh = _CACHE.get("nifty50")
        if cached and fresh and time.time() - fresh[0] <= _STALE_SECONDS:
            return cached
        return _build_board()


def index_quotes() -> list[dict]:
    fresh = _CACHE.get("nifty50")
    saved = fresh[1].get("indices") if fresh else None
    if saved and time.time() - fresh[0] <= _STALE_SECONDS:
        return saved
    return _index_rows()


def _index_rows() -> list[dict]:
    rows = _fetch_many([(item["id"], item["yahoo"]) for item in INDICES])
    named = {item["id"]: item for item in INDICES}
    for row in rows:
        meta = named.get(row["display_symbol"], {})
        row["name"] = meta.get("name")
        row["tradingview"] = meta.get("tradingview")
    return rows


def banking_quotes() -> list[dict]:
    pairs = []
    for symbol in BANKING_WATCH:
        known = BY_SYMBOL[symbol]
        pairs.append((symbol, known.yahoo))
    return _fetch_many(pairs)
