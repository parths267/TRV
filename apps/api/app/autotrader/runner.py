"""Automatic paper runner. Every minute it manages stops; every closed 5-minute bar it looks for entries.

Live orders are never sent. Create data/autotrader/STOP to close the open position and halt entries.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import logging
import time
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from app.providers.upstox import UpstoxError, load_token, token_info

from . import notify
from .engine import CFG, Engine
from .upstox_feed import DATA, UpstoxFeed, choose_underlying, contracts_for, ist_now

log = logging.getLogger("bazaar.autotrader")
STATE = DATA / "state.json"
STATUS = DATA / "status.json"
TRADES = DATA / "trades.csv"
DECISIONS = DATA / "decisions.jsonl"
STOP = DATA / "STOP"
_FIELDS = [
    "date", "instrument", "expiry", "mode", "side", "t_in", "t_out", "reason",
    "legs", "gross", "fees", "net", "score", "why", "priced",
]


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, default=str, indent=2), encoding="utf-8")
    temp.replace(path)


def _append_trade(row: dict) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    fresh = not TRADES.exists()
    with TRADES.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=_FIELDS)
        if fresh:
            writer.writeheader()
        writer.writerow({key: row.get(key) for key in _FIELDS})


def _record_exit(row: dict, engine: Engine) -> None:
    _append_trade(row)
    notify.send(notify.closed_text(row, engine))


def _morning_results(now: dt.datetime, checked: set) -> None:
    """At 08:00 IST send today's result meetings once. Days with none send nothing."""
    day = now.date().isoformat()
    if day in checked or not (dt.time(8, 0) <= now.time() <= dt.time(11, 0)):
        return
    rows = notify.results_for(now.date())
    if rows is None:
        return
    checked.add(day)
    if rows:
        notify.send_once(day, "results", notify.results_text(now.date(), rows))


def _append_decision(entry: dict) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    with DECISIONS.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, default=str) + "\n")
    lines = DECISIONS.read_text(encoding="utf-8").splitlines()
    if len(lines) > 500:
        DECISIONS.write_text("\n".join(lines[-300:]) + "\n", encoding="utf-8")


def _load_engine() -> Engine:
    engine = Engine(CFG)
    if STATE.exists():
        try:
            engine.load_state(json.loads(STATE.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError) as exc:
            log.warning("Paper state could not be read: %s", exc)
    return engine


def _status(state: str, message: str, **extra) -> None:
    _write_json(STATUS, {
        "state": state,
        "message": message,
        "heartbeat": ist_now().isoformat(),
        "paper": True,
        "live_trading_enabled": False,
        "mode": CFG["mode"],
        "upstox": token_info(),
        **extra,
    })


def _sleep_until_next_minute(offset: int = 3) -> None:
    now = time.time()
    time.sleep(max(1.0, 60 - (now % 60) + offset))


def run(max_loops: Optional[int] = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    engine = _load_engine()
    feed: Optional[UpstoxFeed] = None
    feed_day = ""
    last_bar: Optional[dt.datetime] = None
    results_checked: set = set()
    loops = 0
    while max_loops is None or loops < max_loops:
        loops += 1
        now = ist_now()
        today = now.date()
        day = today.isoformat()
        if engine.day != day:
            if engine.pos is not None:
                stale = engine.pos
                engine.pos = None
                _append_trade({
                    "date": stale.ts_in[:10], "instrument": stale.symbol, "expiry": stale.expiry,
                    "mode": stale.mode, "side": stale.side, "t_in": stale.ts_in[11:19], "t_out": "",
                    "reason": "STALE_UNPRICED", "legs": " | ".join(f"{l.strike}{l.typ}" for l in stale.legs),
                    "gross": "", "fees": "", "net": "", "score": stale.score, "why": stale.why, "priced": "none",
                })
            engine.new_day(day)
            feed = None
            last_bar = None
        try:
            _morning_results(now, results_checked)
        except Exception:
            log.exception("Morning results message failed")
        try:
            if today.weekday() >= 5:
                _status("idle", "Weekend. The cash market is closed.")
                _write_json(STATE, engine.to_state())
                time.sleep(120)
                continue
            if dt.time(8, 45) <= now.time() <= dt.time(15, 31):
                load_token()
            if not (dt.time(9, 15) <= now.time() <= dt.time(15, 31)):
                _status("idle", "Outside market hours. Entries run 09:45 to 13:30 IST.")
                _write_json(STATE, engine.to_state())
                time.sleep(120)
                continue
            if not load_token():
                info = token_info()
                if info["auto_login"]:
                    message = f"Automatic Upstox login failed: {info['auto_login_error']}. Retrying every 5 minutes."
                else:
                    message = "Upstox login is needed. Set UPSTOX_PIN and UPSTOX_TOTP_SECRET, or sign in at /api/v1/upstox/login."
                _status("login_needed", message)
                notify.send_once(day, "login", f"⚠️ Stoxs8 auto trader: {message}\nManual login: http://127.0.0.1:8000/api/v1/upstox/login")
                time.sleep(60)
                continue
            if feed is None or feed_day != day:
                pick = choose_underlying(today, CFG["underlyings"], CFG["max_dte"], contracts_for)
                if pick is None:
                    _status("no_expiry", "No index has an option expiry within one day. No trade today.")
                    _write_json(STATE, engine.to_state())
                    time.sleep(900)
                    continue
                feed = UpstoxFeed(pick, today, STOP)
                feed_day = day
                log.info("Trading %s expiry %s, lot %s", pick["symbol"], pick["expiry"], pick["lot_size"])

            feed.refresh_chain()
            bars = feed.bars(5)
            bar_due = not bars or (now - bars[-1].ts).total_seconds() >= 300
            if bar_due:
                feed.refresh_bars()
            exit_row = engine.manage(feed)
            if exit_row:
                _record_exit(exit_row, engine)

            newest = feed.bars(5)[-1].ts if feed.bars(5) else None
            decision = None
            if newest is not None and newest != last_bar:
                last_bar = newest
                was_flat = engine.pos is None
                decision, bar_exit = engine.on_bar(feed)
                if bar_exit:
                    _record_exit(bar_exit, engine)
                if was_flat and engine.pos is not None:
                    notify.send(notify.opened_text(engine.pos))
                if decision is not None:
                    _append_decision({
                        "at": now.isoformat(), "bar": newest.isoformat(), "symbol": feed.symbol,
                        "side": decision.side, "score": decision.score, "why": decision.why,
                        "factors": decision.factors,
                    })

            _write_json(STATE, engine.to_state())
            _status(
                "running", "Paper trading is running.",
                symbol=feed.symbol, expiry=feed.expiry, lot_size=feed.lot_size, spot=feed.spot(),
                position=None if engine.pos is None else asdict(engine.pos),
                last_decision=None if decision is None else {"side": decision.side, "score": decision.score, "why": decision.why},
                trades_today=engine.n_trades, day_pnl=round(engine.day_pnl, 2),
                stop_file=STOP.exists(),
            )
        except UpstoxError as exc:
            _status("error", f"Upstox: {exc.message}")
            log.warning("Upstox error: %s", exc.message)
            if exc.status == 401:
                feed = None
        except Exception as exc:
            _status("error", f"{type(exc).__name__}: {exc}")
            log.exception("Paper runner step failed")
        _sleep_until_next_minute()
