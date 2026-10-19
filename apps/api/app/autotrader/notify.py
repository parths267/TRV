"""Telegram messages for the paper auto trader. Sending runs in a background thread and never blocks trading."""
from __future__ import annotations

import datetime as dt
import json
import logging
import threading
from typing import Optional

from app.config import get_settings

from .upstox_feed import DATA

log = logging.getLogger("bazaar.autotrader.notify")
SENT = DATA / "notified.json"


def _chat_ids() -> list[str]:
    settings = get_settings()
    if settings.telegram_chat_id:
        return [settings.telegram_chat_id.strip()]
    from app.db import SessionLocal
    from app.models import User

    with SessionLocal() as db:
        rows = db.query(User.telegram_chat_id).filter(User.role == "admin", User.telegram_chat_id.isnot(None)).all()
    return sorted({row[0].strip() for row in rows if row[0] and row[0].strip()})


def configured() -> bool:
    return bool(get_settings().telegram_bot_token) and bool(_chat_ids())


def _post(token: str, chat_id: str, text: str) -> Optional[str]:
    import httpx

    try:
        response = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text[:4000], "disable_web_page_preview": True},
            timeout=10,
        )
        if response.status_code != 200:
            return f"Telegram answered {response.status_code}: {response.text[:200]}"
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
    return None


def send_now(text: str) -> list[str]:
    """Send synchronously and return the errors. Used by the test endpoint."""
    token = get_settings().telegram_bot_token
    if not token:
        return ["TELEGRAM_BOT_TOKEN is not set"]
    chats = _chat_ids()
    if not chats:
        return ["No Telegram chat id: set it in Settings for an admin account, or TELEGRAM_CHAT_ID in .env"]
    return [error for chat in chats if (error := _post(token, chat, text))]


def send(text: str) -> None:
    if not get_settings().telegram_bot_token:
        return

    def work() -> None:
        try:
            for error in send_now(text):
                log.warning("Telegram message failed: %s", error)
        except Exception:
            log.exception("Telegram message failed")

    threading.Thread(target=work, daemon=True).start()


def send_once(day: str, key: str, text: str) -> None:
    """Send at most once per day for each key, across restarts."""
    if not configured():
        return
    try:
        sent = json.loads(SENT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        sent = {}
    if sent.get("day") != day:
        sent = {"day": day, "keys": []}
    if key in sent["keys"]:
        return
    sent["keys"].append(key)
    SENT.parent.mkdir(parents=True, exist_ok=True)
    SENT.write_text(json.dumps(sent), encoding="utf-8")
    send(text)


def _rupees(value: float) -> str:
    sign = "-" if value < 0 else "+"
    return f"{sign}₹{abs(value):,.0f}"


def opened_text(pos) -> str:
    view = "bullish" if pos.side == "CALL" else "bearish"
    legs = "\n".join(f"  {'SELL' if leg.qty < 0 else 'BUY'} {leg.strike} {leg.typ} @ {leg.entry:.2f}" for leg in pos.legs)
    if pos.mode == "spread":
        credit = sum(-leg.qty * leg.entry for leg in pos.legs)
        price = f"Credit {credit:.2f} x {pos.mult} = ₹{credit * pos.mult:,.0f}"
    else:
        price = f"Debit {pos.legs[0].entry:.2f} x {pos.mult} = ₹{pos.legs[0].entry * pos.mult:,.0f}"
    return (
        f"🟢 PAPER ENTRY · {pos.symbol} {pos.expiry}\n"
        f"{view.capitalize()} {pos.mode}, score {pos.score}\n{legs}\n{price}\n"
        f"Target ₹{pos.tp * pos.mult:,.0f} · stop ₹{pos.sl * pos.mult:,.0f}\n"
        f"Why: {pos.why}"
    )


_REASONS = {
    "TP": "target hit", "SL": "stop loss", "EOD": "end-of-day square-off", "STOP": "stop requested",
    "INVALID": "breakout failed", "TIME": "time stop", "NO_QUOTE": "quotes missing, priced at last mark",
}


def closed_text(row: dict, engine) -> str:
    net = float(row["net"])
    mark = "✅" if net > 0 else "🔴"
    return (
        f"{mark} PAPER EXIT · {row['instrument']} {row['side']} {row['mode']}\n"
        f"{_REASONS.get(row['reason'], row['reason'])} at {row['t_out']} (in {row['t_in']})\n"
        f"{row['legs']}\n"
        f"Net {_rupees(net)} after ₹{float(row['fees']):,.0f} costs\n"
        f"Today: {engine.n_trades} trades, {_rupees(engine.day_pnl)}"
    )


def results_text(day: dt.date, rows: list[dict], label: str = "today") -> str:
    lines = [f"📅 Results {label} · {day.strftime('%a %d %b %Y')}", f"{len(rows)} of the top 250 companies hold result board meetings:"]
    for index, row in enumerate(rows, 1):
        lines.append(f"{index}. {row['company'] or row['symbol']} ({row['symbol']})")
    lines.append("Source: NSE event calendar. Meeting dates can change; check the exchange filing before trading.")
    return "\n".join(lines)


def results_for(day: dt.date) -> Optional[list[dict]]:
    """Result meetings on one day, or None when the NSE calendar could not be read."""
    import asyncio

    from app.providers.events import fetch_upcoming_results

    body = asyncio.run(fetch_upcoming_results())
    if body.get("status") != "ok":
        log.warning("NSE results calendar unavailable: %s", body.get("reason"))
        return None
    return [row for row in body["results"] if row["date"] == day.isoformat()]
