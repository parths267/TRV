"""Watchlists, holdings, alerts, paper trading, and admin plan changes."""
from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import audit, get_current_user, require_admin
from app.limits import PLANS, assert_under_cap, count_alerts, count_watchlists, plan_limit
from app.market.universe import BY_SYMBOL, yahoo_for
from app.models import AlertRule, Holding, Notification, PaperOrder, PaperPosition, User, Watchlist, WatchlistItem
from app.providers.registry import quotes
from app.services.alerts import evaluate_rule, evaluate_user_rules
from app.services.paper import get_or_create_account, place_paper_order

router = APIRouter(prefix="/api/v1", tags=["account"])


class WatchlistIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class SymbolIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    exchange: str = "NSE"


class HoldingIn(BaseModel):
    symbol: str
    quantity: float
    avg_price: float
    sector: str | None = None


class AlertIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: str
    config: dict
    channels: list[str] = Field(default_factory=lambda: ["in_app"])
    cooldown_seconds: int = 3600
    priority: str = "normal"
    session_only: bool = False


class PaperIn(BaseModel):
    symbol: str
    side: str
    quantity: float
    allow_short: bool = False
    slippage_pct: float | None = None


class PlanIn(BaseModel):
    plan: str


def _owned_list(db: Session, user: User, watchlist_id: str) -> Watchlist:
    row = db.get(Watchlist, watchlist_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    return row


@router.get("/watchlists")
def list_watchlists(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Watchlist).where(Watchlist.user_id == user.id)).all()
    return {"watchlists": [_watch(row) for row in rows]}


@router.post("/watchlists")
def create_watchlist(body: WatchlistIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    assert_under_cap(count_watchlists(db, user.id), user.plan, "watchlists", "Watchlist limit reached.")
    row = Watchlist(user_id=user.id, name=body.name.strip())
    db.add(row)
    db.commit()
    db.refresh(row)
    audit(db, user.id, "watchlist_create", row.id)
    return _watch(row)


@router.delete("/watchlists/{watchlist_id}")
def delete_watchlist(watchlist_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _owned_list(db, user, watchlist_id)
    db.delete(row)
    db.commit()
    return {"deleted": True}


@router.post("/watchlists/{watchlist_id}/symbols")
def add_symbol(
    watchlist_id: str,
    body: SymbolIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _owned_list(db, user, watchlist_id)
    if len(row.items) >= plan_limit(user.plan, "symbols_per_list"):
        raise HTTPException(status_code=402, detail="This watchlist is at the plan's symbol limit.")
    symbol = body.symbol.upper().strip()
    if any(item.symbol == symbol for item in row.items):
        return _watch(row)
    db.add(WatchlistItem(watchlist_id=row.id, symbol=symbol, exchange=body.exchange.upper()))
    db.commit()
    db.refresh(row)
    return _watch(row)


@router.delete("/watchlists/{watchlist_id}/symbols/{symbol}")
def remove_symbol(
    watchlist_id: str,
    symbol: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _owned_list(db, user, watchlist_id)
    for item in list(row.items):
        if item.symbol == symbol.upper():
            db.delete(item)
    db.commit()
    db.refresh(row)
    return _watch(row)


@router.get("/portfolio")
def portfolio(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    holdings = db.scalars(select(Holding).where(Holding.user_id == user.id)).all()
    rows = []
    invested = 0.0
    market_value = 0.0
    sectors: dict[str, float] = {}
    for holding in holdings:
        quote = quotes().get_quote(yahoo_for(holding.symbol))
        price = quote.get("price")
        cost = holding.avg_price * holding.quantity
        value = None if price is None else price * holding.quantity
        invested += cost
        if value is not None:
            market_value += value
            sectors[holding.sector] = sectors.get(holding.sector, 0) + value
        rows.append(
            {
                "symbol": holding.symbol,
                "quantity": holding.quantity,
                "avg_price": holding.avg_price,
                "sector": holding.sector,
                "last_price": price,
                "market_value": None if value is None else round(value, 2),
                "unrealized_pnl": None if value is None else round(value - cost, 2),
                "quote_error": quote.get("error"),
                "as_of": quote.get("market_time"),
                "provider": quote.get("provider"),
            }
        )
    weights = [
        {"sector": name, "weight_pct": round(value / market_value * 100, 2)}
        for name, value in sectors.items()
        if market_value
    ]
    return {
        "holdings": rows,
        "invested": round(invested, 2),
        "market_value": round(market_value, 2) if rows else 0,
        "unrealized_pnl": round(market_value - invested, 2) if market_value else None,
        "sector_weights": weights,
        "realized_pnl": None,
        "realized_note": "Realized P&L needs a sell history. CSV holdings only store the current average cost.",
        "benchmark": "^NSEI",
    }


@router.post("/portfolio/holdings")
def add_holding(body: HoldingIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.quantity <= 0 or body.avg_price <= 0:
        raise HTTPException(status_code=400, detail="quantity and avg_price must be positive")
    symbol = body.symbol.upper()
    row = db.scalar(select(Holding).where(Holding.user_id == user.id, Holding.symbol == symbol))
    if row is None:
        count = len(db.scalars(select(Holding).where(Holding.user_id == user.id)).all())
        assert_under_cap(count, user.plan, "holdings", "Holding limit reached.")
    sector = body.sector or (BY_SYMBOL[symbol].sector if symbol in BY_SYMBOL else "Unclassified")
    if row is None:
        row = Holding(user_id=user.id, symbol=symbol, quantity=body.quantity, avg_price=body.avg_price, sector=sector)
        db.add(row)
    else:
        row.quantity = body.quantity
        row.avg_price = body.avg_price
        row.sector = sector
    db.commit()
    return {"saved": symbol}


@router.post("/portfolio/import")
async def import_csv(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    raw = (await file.read()).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(raw))
    saved = 0
    for record in reader:
        symbol = (record.get("symbol") or "").upper().strip()
        if not symbol:
            continue
        count = len(db.scalars(select(Holding).where(Holding.user_id == user.id)).all())
        existing = db.scalar(select(Holding).where(Holding.user_id == user.id, Holding.symbol == symbol))
        if existing is None:
            assert_under_cap(count, user.plan, "holdings", "Holding limit reached during import.")
        quantity = float(record["quantity"])
        avg_price = float(record["avg_price"])
        sector = record.get("sector") or (BY_SYMBOL[symbol].sector if symbol in BY_SYMBOL else "Unclassified")
        if existing is None:
            db.add(Holding(user_id=user.id, symbol=symbol, quantity=quantity, avg_price=avg_price, sector=sector))
        else:
            existing.quantity = quantity
            existing.avg_price = avg_price
            existing.sector = sector
        saved += 1
    db.commit()
    audit(db, user.id, "portfolio_import", str(saved))
    return {"imported": saved}


@router.get("/alerts")
def list_alerts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(AlertRule).where(AlertRule.user_id == user.id)).all()
    return {"alerts": [_alert(row) for row in rows]}


@router.post("/alerts")
def create_alert(body: AlertIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.kind not in {"price", "scanner"}:
        raise HTTPException(status_code=400, detail="kind must be price or scanner")
    if body.cooldown_seconds < 60:
        raise HTTPException(status_code=400, detail="cooldown_seconds must be at least 60")
    assert_under_cap(count_alerts(db, user.id), user.plan, "alerts", "Alert limit reached.")
    row = AlertRule(
        user_id=user.id,
        name=body.name,
        kind=body.kind,
        config_json=json.dumps(body.config),
        channels_json=json.dumps(body.channels),
        cooldown_seconds=body.cooldown_seconds,
        priority=body.priority,
        session_only=body.session_only,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    audit(db, user.id, "alert_create", row.id)
    return _alert(row)


@router.delete("/alerts/{alert_id}")
def delete_alert(alert_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(AlertRule, alert_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Alert not found")
    db.delete(row)
    db.commit()
    return {"deleted": True}


@router.post("/alerts/evaluate")
def evaluate(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"results": evaluate_user_rules(db, user)}


@router.post("/alerts/{alert_id}/evaluate")
def evaluate_one(alert_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(AlertRule, alert_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Alert not found")
    return evaluate_rule(db, row, user)


@router.get("/notifications")
def notifications(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc())
    ).all()
    return {
        "notifications": [
            {
                "id": row.id,
                "title": row.title,
                "body": row.body,
                "read": row.read,
                "created_at": row.created_at.isoformat(),
                "payload": json.loads(row.payload_json or "{}"),
            }
            for row in rows[:100]
        ]
    }


@router.post("/notifications/{notification_id}/read")
def mark_read(notification_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(Notification, notification_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Notification not found")
    row.read = True
    db.commit()
    return {"read": True}


@router.get("/paper")
def paper_state(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    account = get_or_create_account(db, user)
    positions = db.scalars(select(PaperPosition).where(PaperPosition.user_id == user.id)).all()
    orders = db.scalars(
        select(PaperOrder).where(PaperOrder.user_id == user.id).order_by(PaperOrder.created_at.desc())
    ).all()
    marked = []
    for position in positions:
        quote = quotes().get_quote(yahoo_for(position.symbol))
        price = quote.get("price")
        unrealized = None if price is None else round((price - position.avg_price) * position.quantity, 2)
        marked.append(
            {
                "symbol": position.symbol,
                "quantity": position.quantity,
                "avg_price": position.avg_price,
                "last_price": price,
                "unrealized_pnl": unrealized,
                "realized_pnl": round(position.realized_pnl, 2),
                "as_of": quote.get("market_time"),
            }
        )
    return {
        "paper": True,
        "live_trading_enabled": False,
        "cash": round(account.cash, 2),
        "currency": account.currency,
        "positions": marked,
        "orders": [
            {
                "id": order.id,
                "symbol": order.symbol,
                "side": order.side,
                "quantity": order.quantity,
                "fill_price": order.fill_price,
                "fees": order.fees,
                "data_as_of": order.data_as_of,
                "quote_stale": order.quote_stale,
                "note": order.note,
                "created_at": order.created_at.isoformat(),
            }
            for order in orders[:50]
        ],
    }


@router.post("/paper/orders")
def paper_order(body: PaperIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    result = place_paper_order(
        db,
        user,
        symbol=body.symbol,
        side=body.side,
        quantity=body.quantity,
        allow_short=body.allow_short,
        slippage_pct=body.slippage_pct,
    )
    audit(db, user.id, "paper_order", f"{body.side} {body.symbol}")
    return result


@router.get("/admin/users")
def admin_users(_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(User)).all()
    return {
        "users": [
            {"id": row.id, "email": row.email, "plan": row.plan, "role": row.role, "verified": row.email_verified}
            for row in rows
        ]
    }


@router.patch("/admin/users/{user_id}/plan")
def admin_plan(
    user_id: str,
    body: PlanIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if body.plan not in PLANS:
        raise HTTPException(status_code=400, detail="Unknown plan")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.plan = body.plan
    db.commit()
    audit(db, admin.id, "plan_change", f"{user.email}:{body.plan}")
    return {"id": user.id, "plan": user.plan}


def _watch(row: Watchlist) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "items": [{"symbol": item.symbol, "exchange": item.exchange} for item in row.items],
    }


def _alert(row: AlertRule) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "kind": row.kind,
        "config": json.loads(row.config_json),
        "channels": json.loads(row.channels_json),
        "cooldown_seconds": row.cooldown_seconds,
        "enabled": row.enabled,
        "priority": row.priority,
        "session_only": row.session_only,
        "last_fingerprint": row.last_fingerprint,
        "last_triggered_at": None if row.last_triggered_at is None else row.last_triggered_at.isoformat(),
    }
