"""In-process scheduler. Production can run the same job in a separate process.

Opening the website does not start this loop. The API process does, when
SCHEDULER_ENABLED is true.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.models import User
from app.services.alerts import evaluate_user_rules

log = logging.getLogger("bazaar.worker")


def evaluate_all() -> None:
    db = SessionLocal()
    try:
        users = db.scalars(select(User)).all()
        for user in users:
            try:
                evaluate_user_rules(db, user)
            except Exception:
                log.exception("alert evaluation failed for %s", user.id)
    finally:
        db.close()


def start_scheduler() -> AsyncIOScheduler:
    settings = get_settings()
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        evaluate_all,
        "interval",
        minutes=max(1, settings.scan_interval_minutes),
        id="alerts",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    log.info("alert scheduler started every %s minutes", settings.scan_interval_minutes)
    return scheduler
