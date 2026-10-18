"""Clock-based NSE/BSE session status.

Holiday calendars are not bundled. A weekday that is an exchange holiday is
reported as open unless the operator loads a calendar. The payload says so.
"""
from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

PRE_OPEN = time(9, 0)
REGULAR_OPEN = time(9, 15)
REGULAR_CLOSE = time(15, 30)


def session_status(now: datetime | None = None) -> dict:
    current = now.astimezone(IST) if now else datetime.now(IST)
    clock = current.time()
    weekday = current.weekday()
    if weekday >= 5:
        state = "closed"
        label = "Weekend — cash market closed"
    elif clock < PRE_OPEN or clock >= REGULAR_CLOSE:
        state = "closed"
        label = "Cash market closed"
    elif clock < REGULAR_OPEN:
        state = "pre_open"
        label = "Pre-open session"
    else:
        state = "regular"
        label = "Regular session"
    return {
        "state": state,
        "label": label,
        "timezone": "Asia/Kolkata",
        "as_of": current.isoformat(),
        "regular_hours": "09:15–15:30 IST",
        "holiday_calendar": "not_loaded",
        "limitation": (
            "Session status uses the clock only. Exchange holidays are not applied, "
            "so a weekday holiday can be shown as open."
        ),
    }


def in_quiet_hours(quiet_start: str | None, quiet_end: str | None, now: datetime | None = None) -> bool:
    if not quiet_start or not quiet_end:
        return False
    current = (now.astimezone(IST) if now else datetime.now(IST)).time()
    try:
        start = time.fromisoformat(quiet_start)
        end = time.fromisoformat(quiet_end)
    except ValueError:
        return False
    if start <= end:
        return start <= current < end
    return current >= start or current < end
