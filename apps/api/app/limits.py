"""Plan entitlements enforced on the server."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AlertRule, SavedStrategy, UsageCounter, Watchlist

PLANS: dict[str, dict[str, int]] = {
    "free": {
        "watchlists": 2,
        "symbols_per_list": 15,
        "alerts": 3,
        "strategies": 1,
        "backtests_per_day": 0,
        "scanner_runs_per_day": 8,
        "holdings": 20,
    },
    "pro": {
        "watchlists": 10,
        "symbols_per_list": 50,
        "alerts": 25,
        "strategies": 10,
        "backtests_per_day": 40,
        "scanner_runs_per_day": 80,
        "holdings": 100,
    },
    "premium": {
        "watchlists": 40,
        "symbols_per_list": 150,
        "alerts": 150,
        "strategies": 50,
        "backtests_per_day": 300,
        "scanner_runs_per_day": 400,
        "holdings": 500,
    },
}


def plan_limit(plan: str, key: str) -> int:
    table = PLANS.get(plan) or PLANS["free"]
    return table[key]


def assert_under_cap(current: int, plan: str, key: str, message: str) -> None:
    limit = plan_limit(plan, key)
    if current >= limit:
        raise HTTPException(status_code=402, detail=f"{message} Limit for the {plan} plan is {limit}.")


def consume_daily(db: Session, user_id: str, plan: str, metric: str) -> None:
    limit = plan_limit(plan, metric)
    if limit <= 0:
        raise HTTPException(
            status_code=402,
            detail=f"{metric.replace('_', ' ')} is not included on the {plan} plan.",
        )
    period = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    row = db.scalar(
        select(UsageCounter).where(
            UsageCounter.user_id == user_id,
            UsageCounter.metric == metric,
            UsageCounter.period == period,
        )
    )
    if row is None:
        row = UsageCounter(user_id=user_id, metric=metric, period=period, count=0)
        db.add(row)
    if row.count >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"Daily {metric.replace('_', ' ')} limit reached ({limit} on the {plan} plan).",
        )
    row.count += 1
    db.commit()


def count_watchlists(db: Session, user_id: str) -> int:
    return int(
        db.scalar(select(func.count()).select_from(Watchlist).where(Watchlist.user_id == user_id))
        or 0
    )


def count_alerts(db: Session, user_id: str) -> int:
    return int(
        db.scalar(select(func.count()).select_from(AlertRule).where(AlertRule.user_id == user_id))
        or 0
    )


def count_strategies(db: Session, user_id: str) -> int:
    return int(
        db.scalar(
            select(func.count()).select_from(SavedStrategy).where(SavedStrategy.user_id == user_id)
        )
        or 0
    )
