"""Dashboard, search, quotes, and candles."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.deps import get_current_user
from app.security import decode_access_token
from app.market.session import session_status
from app.market.universe import BY_SYMBOL, NIFTY_50, SNAPSHOT_NOTE, yahoo_for
from app.models import User
from app.providers.registry import provider_status, quotes
from app.providers.upstox import UpstoxError
from app.services.board import index_quotes, universe_board
from app.services.options import build_chain

router = APIRouter(prefix="/api/v1/market", tags=["market"])


def meta(**extra) -> dict:
    settings = get_settings()
    return {
        "data_mode": settings.data_mode,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "live_trading_enabled": False,
        "delayed": not settings.demo_mode,
        **extra,
    }


@router.get("/session")
def session(_user: User = Depends(get_current_user)):
    return {"session": session_status(), "meta": meta()}


@router.get("/status")
def status(_user: User = Depends(get_current_user)):
    return {"providers": provider_status(), "meta": meta()}


@router.get("/pulse")
def pulse(_user: User = Depends(get_current_user)):
    """Latest index quotes. This is still a delayed snapshot, not a millisecond tape."""
    return {"indices": index_quotes(), "meta": meta()}


@router.get("/dashboard")
def dashboard(user: User = Depends(get_current_user)):
    board = universe_board()
    indices = board.get("indices") or index_quotes()
    return {
        "session": session_status(),
        "indices": indices,
        "breadth": board["breadth"],
        "heatmap": board["heatmap"],
        "gainers": board["gainers"],
        "losers": board["losers"],
        "approaching_52w_provider": board["approaching_52w_provider"],
        "failures": board["failures"],
        "universe_note": SNAPSHOT_NOTE,
        "meta": meta(provider=quotes().health()["provider"] if hasattr(quotes(), "health") else "quotes"),
        "viewer": user.plan,
    }


@router.get("/search")
def search(q: str = Query(min_length=1, max_length=32), _user: User = Depends(get_current_user)):
    query = q.strip().upper()
    matches: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def add(row: dict) -> None:
        key = (row["exchange"], row["symbol"])
        if key in seen:
            return
        seen.add(key)
        matches.append(row)

    for item in NIFTY_50:
        if query in item.symbol or query in item.name.upper():
            add(item.as_dict() | {"list": "nifty50_snapshot"})
    coinlist_error = None
    try:
        from tradingview_mcp.core.services.coinlist import load_symbols

        for exchange in ("nse", "bse"):
            for raw in load_symbols(exchange):
                symbol = raw.split(":", 1)[-1]
                if query not in symbol:
                    continue
                known = BY_SYMBOL.get(symbol)
                add(
                    {
                        "symbol": symbol,
                        "name": known.name if known else None,
                        "exchange": exchange.upper(),
                        "yahoo": yahoo_for(symbol, exchange.upper()),
                        "list": "engine_coinlist",
                    }
                )
    except Exception as exc:
        coinlist_error = str(exc)

    def rank(row: dict) -> tuple:
        symbol = row["symbol"]
        name = (row.get("name") or "").upper()
        if symbol == query or name == query:
            bucket = 0
        elif name.startswith(query) or symbol.startswith(query):
            bucket = 1
        elif query in name:
            bucket = 2
        elif query in symbol:
            bucket = 3
        else:
            bucket = 4
        named = 0 if name else 1
        nifty = 0 if row.get("list") == "nifty50_snapshot" else 1
        return (bucket, named, nifty, len(symbol), symbol)

    matches.sort(key=rank)
    collapsed: list[dict] = []
    grouped: dict[str, dict] = {}
    for row in matches:
        current = grouped.get(row["symbol"])
        if current is None:
            current = dict(row)
            current["exchanges"] = [row["exchange"]]
            grouped[row["symbol"]] = current
            collapsed.append(current)
            continue
        if row["exchange"] not in current["exchanges"]:
            current["exchanges"].append(row["exchange"])
        if not current.get("name") and row.get("name"):
            current["name"] = row["name"]
    for row in collapsed:
        row["exchange"] = "NSE" if "NSE" in row["exchanges"] else row["exchanges"][0]
    payload: dict = {"results": collapsed[:8], "meta": meta()}
    if coinlist_error:
        payload["coinlist_error"] = coinlist_error
    return payload


@router.get("/quote")
def quote(symbol: str, exchange: str = "NSE", _user: User = Depends(get_current_user)):
    row = quotes().get_quote(yahoo_for(symbol, exchange))
    if row.get("error") or row.get("price") is None:
        raise HTTPException(status_code=502, detail=row.get("error") or "No price returned")
    known = BY_SYMBOL.get(symbol.upper())
    if known:
        row["company"] = known.name
        row["sector"] = known.sector
    return {"quote": row, "meta": meta(provider=row.get("provider"), as_of=row.get("market_time"), stale=row.get("quote_stale"))}


@router.get("/candles")
def candles(
    symbol: str,
    interval: str = "1d",
    exchange: str = "NSE",
    _user: User = Depends(get_current_user),
):
    history = quotes().get_candles(yahoo_for(symbol, exchange), interval)
    return {
        "symbol": symbol.upper(),
        "history": history,
        "meta": meta(provider=history.get("provider"), stale=bool(history.get("error"))),
    }


@router.get("/options")
def option_chain(
    index: str = Query(min_length=1, max_length=32),
    expiry: str = Query(default=""),
    _user: User = Depends(get_current_user),
):
    try:
        body = build_chain(index, expiry or None)
    except UpstoxError as exc:
        status = exc.status if 400 <= exc.status <= 599 else 502
        raise HTTPException(status_code=status, detail=exc.message) from exc
    return {**body, "meta": meta(source="upstox")}


@router.get("/stream")
async def stream(token: str = Query(min_length=10)):
    """Server-sent index quotes. EventSource cannot set an Authorization header."""
    db = SessionLocal()
    try:
        payload = decode_access_token(token)
        user = db.get(User, payload.get("sub"))
        if user is None:
            raise HTTPException(status_code=401, detail="Invalid session")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid session") from exc
    finally:
        db.close()

    async def events():
        for _ in range(4):
            rows = index_quotes()
            packet = {"indices": rows, "session": session_status(), "meta": meta()}
            yield f"data: {json.dumps(packet, default=str)}\n\n"
            await asyncio.sleep(20)

    return StreamingResponse(events(), media_type="text/event-stream")
