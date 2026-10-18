"""Alert evaluation with cooldown and re-arm. The scheduler and the manual endpoint share this."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.market.analysis import ScanRules, alert_allowed
from app.market.session import in_quiet_hours, session_status
from app.market.universe import yahoo_for
from app.models import AlertRule, Notification, User
from app.providers.registry import quotes
from app.services.scans import run_scanner


def _channels(rule: AlertRule) -> list[str]:
    try:
        data = json.loads(rule.channels_json)
    except json.JSONDecodeError:
        return ["in_app"]
    return data if isinstance(data, list) else ["in_app"]


def _config(rule: AlertRule) -> dict:
    try:
        data = json.loads(rule.config_json)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _condition(rule: AlertRule) -> tuple[bool, str, str, dict]:
    """Return triggered, fingerprint, body, payload. Errors become a non-trigger with an explanation."""
    cfg = _config(rule)
    provider = quotes()
    if rule.kind == "price":
        symbol = str(cfg.get("symbol", "")).upper()
        operator = cfg.get("operator", "gte")
        threshold = float(cfg["threshold"])
        quote = provider.get_quote(yahoo_for(symbol, cfg.get("exchange", "NSE")))
        price = quote.get("price")
        if price is None or quote.get("error"):
            return False, "", f"No price for {symbol}: {quote.get('error', 'missing')}", {"quote": quote}
        if quote.get("quote_stale"):
            return False, "", f"Stale quote for {symbol} was not allowed to fire a price alert.", {"quote": quote}
        triggered = price >= threshold if operator == "gte" else price <= threshold
        fingerprint = f"price:{symbol}:{operator}:{threshold}"
        body = f"{symbol} last price {price} is {'at or beyond' if triggered else 'inside'} {threshold}."
        return triggered, fingerprint, body, {"quote": quote, "threshold": threshold}
    if rule.kind == "scanner":
        rules = ScanRules.from_dict(cfg.get("rules") or {})
        interval = cfg.get("interval", "1d")
        symbols = cfg.get("symbols") or []
        if not symbols:
            return False, "", "Scanner alert has no symbols.", {}
        result = run_scanner(symbols, rules, interval)
        names = [row["symbol"] for row in result["qualified"]]
        fingerprint = "scanner:" + ",".join(sorted(names))
        triggered = bool(names)
        body = "Scanner qualified: " + ", ".join(names) if names else "Scanner qualified nobody."
        return triggered, fingerprint, body, {"qualified": names, "interval": interval}
    return False, "", f"Unknown alert kind '{rule.kind}'.", {}


def deliver(db: Session, user: User, rule: AlertRule, title: str, body: str, payload: dict) -> dict:
    channels = _channels(rule)
    skipped = []
    settings = get_settings()
    if "email" in channels and not settings.smtp_host:
        skipped.append("email is not configured")
    if "telegram" in channels and (not settings.telegram_bot_token or not user.telegram_chat_id):
        skipped.append("telegram is not configured")
    note = payload | {"channels": channels, "skipped": skipped, "data_mode": settings.data_mode}
    row = Notification(
        user_id=user.id,
        alert_id=rule.id,
        title=title,
        body=body,
        payload_json=json.dumps(note, default=str),
    )
    db.add(row)
    sent = {"in_app": True, "skipped": skipped}
    if "telegram" in channels and settings.telegram_bot_token and user.telegram_chat_id:
        sent["telegram"] = _telegram(settings.telegram_bot_token, user.telegram_chat_id, f"{title}\n{body}")
    if "email" in channels and settings.smtp_host and settings.smtp_from:
        sent["email"] = _email(user.email, title, body)
    return sent


def _telegram(token: str, chat_id: str, text: str) -> str:
    import httpx

    try:
        response = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text[:4000]},
            timeout=10,
        )
        response.raise_for_status()
        return "sent"
    except Exception as exc:
        return f"failed: {exc}"


def _email(to: str, subject: str, body: str) -> str:
    import smtplib
    from email.message import EmailMessage

    settings = get_settings()
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password or "")
            smtp.send_message(message)
        return "sent"
    except Exception as exc:
        return f"failed: {exc}"


def evaluate_rule(db: Session, rule: AlertRule, user: User, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if not rule.enabled:
        return {"emitted": False, "reason": "disabled"}
    if rule.session_only and session_status(now)["state"] != "regular":
        return {"emitted": False, "reason": "outside the regular session"}
    if in_quiet_hours(user.quiet_start, user.quiet_end, now):
        return {"emitted": False, "reason": "quiet hours"}
    try:
        triggered, fingerprint, body, payload = _condition(rule)
    except Exception as exc:
        return {"emitted": False, "reason": str(exc)}
    if not triggered:
        rule.last_fingerprint = None
        db.commit()
        return {"emitted": False, "reason": body or "condition false", "rearmed": True}
    if not alert_allowed(fingerprint, rule.last_fingerprint, rule.last_triggered_at, rule.cooldown_seconds, now):
        return {"emitted": False, "reason": "cooldown", "fingerprint": fingerprint}
    rule.last_fingerprint = fingerprint
    rule.last_triggered_at = now
    delivery = deliver(db, user, rule, rule.name, body, payload)
    db.commit()
    return {"emitted": True, "fingerprint": fingerprint, "delivery": delivery}


def evaluate_user_rules(db: Session, user: User) -> list[dict]:
    rules = db.query(AlertRule).filter(AlertRule.user_id == user.id, AlertRule.enabled.is_(True)).all()
    return [{"id": rule.id, **evaluate_rule(db, rule, user)} for rule in rules]
