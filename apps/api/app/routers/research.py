"""Scanners, index studies, corporate events, strategies, and the assistant."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import audit, get_current_user
from app.limits import assert_under_cap, consume_daily, count_strategies, plan_limit
from app.market.analysis import ScanRules
from app.market.costs import DEFAULT_COSTS
from app.market.universe import yahoo_for
from app.models import SavedStrategy, User
from app.providers.events import fetch_nse_activity, fetch_upcoming_results
from app.providers.demo import demo_events
from app.config import get_settings
from app.services.assistant import answer_question
from app.services.scans import nifty_symbols, run_highs, run_index_monitor, run_scanner
from app.services.strategy_screens import catalog as screen_catalog
from app.services.strategy_screens import run_screen
from tradingview_mcp.core.services.backtest_service import (
    _STRATEGY_LABELS,
    compare_strategies,
    run_backtest,
    walk_forward_backtest,
)

router = APIRouter(prefix="/api/v1", tags=["research"])


class ScanIn(BaseModel):
    interval: str = "1d"
    rules: dict = Field(default_factory=dict)
    symbols: list[dict] | None = None


class BacktestIn(BaseModel):
    symbol: str
    strategy: str
    period: str = "1y"
    initial_capital: float = 1_000_000
    interval: str = "1d"
    include_trade_log: bool = True
    include_equity_curve: bool = True
    exchange: str = "NSE"


class SaveStrategyIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    engine_strategy: str
    config: dict = Field(default_factory=dict)


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=1000)


class IndexIn(BaseModel):
    threshold_pct: float = -0.6
    window_minutes: int = 10


def _yahoo_symbol(symbol: str, exchange: str) -> str:
    return yahoo_for(symbol, exchange)


def _engine_kwargs() -> dict:
    costs = DEFAULT_COSTS.breakdown()
    return {
        "commission_pct": costs["engine_commission_pct_per_side"],
        "slippage_pct": costs["slippage_pct_per_side"],
        "risk_free_rate": 0.065,
        "periods_per_year": 246,
    }


@router.post("/scanner/run")
def scanner(body: ScanIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.interval != "1d" and user.plan == "free":
        raise HTTPException(status_code=402, detail="Intraday scans are not included on the free plan.")
    if body.interval not in {"1m", "5m", "15m", "30m", "1h", "1d", "1w"}:
        raise HTTPException(status_code=400, detail="Unsupported interval")
    try:
        rules = ScanRules.from_dict(body.rules)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    consume_daily(db, user.id, user.plan, "scanner_runs_per_day")
    symbols = body.symbols or nifty_symbols()
    if len(symbols) > plan_limit(user.plan, "symbols_per_list"):
        raise HTTPException(status_code=402, detail="Symbol list is larger than the plan allows for one scan.")
    result = run_scanner(symbols, rules, body.interval)
    return result | {"meta": {"data_mode": get_settings().data_mode}}


@router.get("/highs")
def highs(approach_pct: float = 2.0, user: User = Depends(get_current_user)):
    if approach_pct <= 0 or approach_pct > 20:
        raise HTTPException(status_code=400, detail="approach_pct must be between 0 and 20")
    return run_highs(approach_pct) | {"meta": {"data_mode": get_settings().data_mode, "viewer": user.plan}}


@router.post("/indices/monitor")
def indices(body: IndexIn, _user: User = Depends(get_current_user)):
    if body.threshold_pct == 0:
        raise HTTPException(status_code=400, detail="threshold_pct cannot be zero")
    try:
        result = run_index_monitor(body.threshold_pct, body.window_minutes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result | {"meta": {"data_mode": get_settings().data_mode}}


@router.get("/results")
async def corporate_results(_user: User = Depends(get_current_user)):
    if get_settings().demo_mode:
        return {
            "status": "demo",
            "provider": "demo",
            "data_mode": "demo",
            "results": [],
            "count": 0,
            "reason": "Demo mode has no exchange result calendar.",
            "source_url": "https://www.nseindia.com/companies-listing/corporate-filings-event-calendar",
        }
    return await fetch_upcoming_results()


@router.get("/events")
async def events(_user: User = Depends(get_current_user)):
    if get_settings().demo_mode:
        return demo_events()
    return await fetch_nse_activity()


@router.get("/strategies/screens")
def screens(_user: User = Depends(get_current_user)):
    return {"screens": screen_catalog()}


@router.get("/strategies/screens/{screen_id}")
def screen(screen_id: str, _user: User = Depends(get_current_user)):
    try:
        return run_screen(screen_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown strategy") from exc


@router.get("/strategies/library")
def library(_user: User = Depends(get_current_user)):
    costs = DEFAULT_COSTS.breakdown()
    return {
        "strategies": [{"id": key, "label": label} for key, label in _STRATEGY_LABELS.items()],
        "costs": costs,
        "limitations": [
            "The engine supports daily and hourly bars from Yahoo Finance, periods 1mo through 2y.",
            "Orders are modeled on the signal bar's close after costs. That is optimistic versus the next bar's open.",
            "Sharpe uses a 6.5% risk-free assumption and 246 sessions for daily bars when this API calls the engine.",
            "A historical result is not evidence the strategy will make money.",
        ],
    }


@router.post("/strategies/backtest")
def backtest(body: BacktestIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    consume_daily(db, user.id, user.plan, "backtests_per_day")
    kwargs = _engine_kwargs()
    if body.interval == "1h":
        kwargs["periods_per_year"] = int(246 * 6.25)
    result = run_backtest(
        _yahoo_symbol(body.symbol, body.exchange),
        body.strategy,
        period=body.period,
        initial_capital=body.initial_capital,
        interval=body.interval,
        include_trade_log=body.include_trade_log,
        include_equity_curve=body.include_equity_curve,
        **kwargs,
    )
    result["display_symbol"] = body.symbol.upper()
    result["cost_model"] = DEFAULT_COSTS.breakdown()
    result["execution_note"] = (
        "The reused engine fills on the same bar's close after percentage costs. "
        "A more conservative model would wait for the next bar's open. Do not treat the result as tradable profit."
    )
    audit(db, user.id, "backtest", body.symbol.upper())
    return result


@router.post("/strategies/compare")
def compare(body: BacktestIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    consume_daily(db, user.id, user.plan, "backtests_per_day")
    kwargs = _engine_kwargs()
    result = compare_strategies(
        _yahoo_symbol(body.symbol, body.exchange),
        period=body.period,
        initial_capital=body.initial_capital,
        interval=body.interval,
        **kwargs,
    )
    result["display_symbol"] = body.symbol.upper()
    result["cost_model"] = DEFAULT_COSTS.breakdown()
    return result


@router.post("/strategies/walk-forward")
def walk(body: BacktestIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.plan == "free":
        raise HTTPException(status_code=402, detail="Walk-forward tests start on the Pro plan.")
    consume_daily(db, user.id, user.plan, "backtests_per_day")
    kwargs = _engine_kwargs()
    return walk_forward_backtest(
        _yahoo_symbol(body.symbol, body.exchange),
        body.strategy,
        period=body.period if body.period in {"1y", "2y"} else "2y",
        initial_capital=body.initial_capital,
        interval=body.interval,
        **kwargs,
    )


@router.get("/strategies")
def list_strategies(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(SavedStrategy).where(SavedStrategy.user_id == user.id)).all()
    return {"strategies": [_dump(row) for row in rows]}


@router.post("/strategies")
def save_strategy(body: SaveStrategyIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.engine_strategy not in _STRATEGY_LABELS:
        raise HTTPException(status_code=400, detail="Unknown engine strategy")
    assert_under_cap(count_strategies(db, user.id), user.plan, "strategies", "Saved strategy limit reached.")
    row = SavedStrategy(
        user_id=user.id,
        name=body.name,
        engine_strategy=body.engine_strategy,
        config_json=json.dumps(body.config),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _dump(row)


@router.delete("/strategies/{strategy_id}")
def delete_strategy(strategy_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(SavedStrategy, strategy_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")
    db.delete(row)
    db.commit()
    return {"deleted": True}


@router.post("/assistant/ask")
def ask(body: AskIn, user: User = Depends(get_current_user)):
    if user.plan == "free":
        raise HTTPException(status_code=402, detail="The research assistant starts on the Pro plan.")
    return answer_question(body.question)


def _dump(row: SavedStrategy) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "engine_strategy": row.engine_strategy,
        "config": json.loads(row.config_json or "{}"),
        "created_at": row.created_at.isoformat(),
    }
