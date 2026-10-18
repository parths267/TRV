"""Paper trading. Fills are simulated from the latest provider quote and are never live orders."""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.market.costs import DEFAULT_COSTS
from app.market.universe import BY_SYMBOL, yahoo_for
from app.models import PaperAccount, PaperOrder, PaperPosition, User
from app.providers.registry import quotes


def get_or_create_account(db: Session, user: User) -> PaperAccount:
    account = db.scalar(select(PaperAccount).where(PaperAccount.user_id == user.id))
    if account is None:
        account = PaperAccount(user_id=user.id)
        db.add(account)
        db.commit()
        db.refresh(account)
    return account


def place_paper_order(
    db: Session,
    user: User,
    *,
    symbol: str,
    side: str,
    quantity: float,
    allow_short: bool = False,
    slippage_pct: float | None = None,
) -> dict:
    symbol = symbol.upper().strip()
    side = side.lower().strip()
    if side not in {"buy", "sell"}:
        raise HTTPException(status_code=400, detail="side must be buy or sell")
    if quantity <= 0:
        raise HTTPException(status_code=400, detail="quantity must be positive")
    if allow_short and user.plan == "free":
        raise HTTPException(status_code=402, detail="Paper shorts are not included on the free plan.")
    quote = quotes().get_quote(yahoo_for(symbol))
    price = quote.get("price")
    if price is None or quote.get("error"):
        raise HTTPException(
            status_code=409,
            detail=f"No quote for {symbol}. The paper order was not filled. {quote.get('error', '')}".strip(),
        )
    slip = DEFAULT_COSTS.slippage_pct if slippage_pct is None else slippage_pct
    if slip < 0 or slip > 5:
        raise HTTPException(status_code=400, detail="slippage_pct must be between 0 and 5")
    fill = price * (1 + slip / 100) if side == "buy" else price * (1 - slip / 100)
    traded = fill * quantity
    fees = DEFAULT_COSTS.fees_inr(side, traded)
    account = get_or_create_account(db, user)
    position = db.scalar(
        select(PaperPosition).where(PaperPosition.user_id == user.id, PaperPosition.symbol == symbol)
    )
    if position is None:
        position = PaperPosition(user_id=user.id, symbol=symbol, quantity=0, avg_price=0, realized_pnl=0)
        db.add(position)

    if side == "buy":
        cost = traded + fees
        if account.cash + 1e-6 < cost:
            raise HTTPException(status_code=400, detail="Paper cash is not enough for this buy.")
        new_qty = position.quantity + quantity
        if position.quantity >= 0:
            position.avg_price = (
                (position.avg_price * position.quantity + fill * quantity) / new_qty if new_qty else 0
            )
        position.quantity = new_qty
        account.cash -= cost
    else:
        if position.quantity + 1e-9 < quantity and not allow_short:
            raise HTTPException(
                status_code=400,
                detail="Sell quantity exceeds the paper long. Pass allow_short only for explicit paper-short research.",
            )
        proceeds = traded - fees
        closing = min(quantity, max(position.quantity, 0))
        if closing:
            position.realized_pnl += (fill - position.avg_price) * closing - fees * (closing / quantity)
        position.quantity -= quantity
        if abs(position.quantity) < 1e-9:
            position.quantity = 0
            position.avg_price = 0
        account.cash += proceeds

    order = PaperOrder(
        user_id=user.id,
        symbol=symbol,
        side=side,
        quantity=quantity,
        fill_price=round(fill, 4),
        fees=fees,
        slippage_pct=slip,
        data_as_of=quote.get("market_time"),
        quote_stale=bool(quote.get("quote_stale")),
        status="filled",
        note="paper fill from delayed or demo quote; not a broker order",
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    sector = BY_SYMBOL[symbol].sector if symbol in BY_SYMBOL else "Unclassified"
    return {
        "order_id": order.id,
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "quote_price": price,
        "fill_price": order.fill_price,
        "fees": fees,
        "slippage_pct": slip,
        "data_as_of": order.data_as_of,
        "quote_stale": order.quote_stale,
        "cash": round(account.cash, 2),
        "position_quantity": position.quantity,
        "sector": sector,
        "paper": True,
        "live_trading_enabled": False,
        "provider": quote.get("provider"),
        "data_mode": quote.get("data_mode", "live"),
    }
