"""Read-only view of the automatic paper trader, plus its stop switch."""
from __future__ import annotations

import csv
import json

from fastapi import APIRouter, Depends, HTTPException

from app.autotrader import notify
from app.autotrader.engine import CFG, summary
from app.autotrader.runner import DECISIONS, STATUS, STOP, TRADES
from app.deps import get_current_user, require_admin
from app.models import User

router = APIRouter(prefix="/api/v1/autotrader", tags=["autotrader"])


def _read_json(path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _trades() -> list[dict]:
    if not TRADES.exists():
        return []
    with TRADES.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _decisions(limit: int = 20) -> list[dict]:
    if not DECISIONS.exists():
        return []
    rows = []
    for line in DECISIONS.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return list(reversed(rows))


@router.get("")
def overview(_user: User = Depends(get_current_user)):
    trades = _trades()
    priced = [row for row in trades if row.get("net") not in (None, "")]
    rules = {
        "mode": CFG["mode"],
        "underlyings": list(CFG["underlyings"]),
        "max_dte": CFG["max_dte"],
        "entry_window": f"{CFG['entry_from'].strftime('%H:%M')}–{CFG['entry_until'].strftime('%H:%M')}",
        "squareoff": CFG["squareoff"].strftime("%H:%M"),
        "min_score": CFG["min_score"],
        "max_trades": CFG["max_trades"],
        "daily_loss_cap": CFG["daily_loss_cap"],
        "max_risk_per_trade": CFG["max_risk_per_trade"],
        "vix_max": CFG["vix_max"],
    }
    return {
        "status": _read_json(STATUS) or {"state": "not_started", "message": "The paper runner has not written a status yet."},
        "stopped": STOP.exists(),
        "summary": summary(priced),
        "trades": list(reversed(trades))[:50],
        "decisions": _decisions(),
        "rules": rules,
        "paper": True,
        "live_trading_enabled": False,
        "telegram": notify.configured(),
    }


@router.post("/telegram-test")
def telegram_test(_admin: User = Depends(require_admin)):
    errors = notify.send_now("✅ Stoxs8 auto trader is connected. Paper entries and exits, and the 08:00 list of companies reporting results, will arrive here.")
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))
    return {"sent": True}


@router.post("/stop")
def stop(_admin: User = Depends(require_admin)):
    STOP.parent.mkdir(parents=True, exist_ok=True)
    STOP.write_text("stop", encoding="utf-8")
    return {"stopped": True}


@router.post("/resume")
def resume(_admin: User = Depends(require_admin)):
    STOP.unlink(missing_ok=True)
    return {"stopped": False}
