"""Run a named screen across the stored broad index snapshot."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

from app.market.screens import (
    BY_ID,
    CATALOG,
    UNAVAILABLE_REASON,
    inside_bar_breakout,
    measure_symbol,
    qualifies,
    sector_leaders,
)
from app.market.universe import BROAD_SNAPSHOT_NOTE, INDICES, broad_universe
from app.providers.registry import quotes

_CACHE: dict[str, tuple[float, dict]] = {}
_BOARD: tuple[float, list[dict], int] | None = None
_NIFTY = next(item for item in INDICES if item["id"] == "nifty50")


def catalog() -> list[dict]:
    return [dict(item) for item in CATALOG]


def run_screen(screen_id: str) -> dict:
    spec = BY_ID.get(screen_id)
    if spec is None:
        raise KeyError(screen_id)
    cached = _CACHE.get(screen_id)
    if cached and time.time() - cached[0] < 180:
        return cached[1]
    body = dict(spec)
    body["universe"] = BROAD_SNAPSHOT_NOTE
    body["stocks"] = []
    body["sectors"] = []
    body["scanned"] = 0
    body["skipped"] = 0
    if spec["status"] != "ready":
        body["reason"] = UNAVAILABLE_REASON[screen_id]
        return _CACHE.setdefault(screen_id, (time.time(), body))[1]

    if screen_id == "inside_15m":
        rows, skipped = _intraday_inside_rows()
    else:
        rows, skipped = _measured_rows()

    sectors: list[dict] = []
    if screen_id == "sector_rotation":
        matched, sectors = sector_leaders(rows)
    else:
        matched = [row for row in rows if qualifies(screen_id, row)]
        matched.sort(key=lambda row: _sort_key(screen_id, row))

    body.update(
        {
            "scanned": len(rows) + skipped,
            "skipped": skipped,
            "matched": len(matched),
            "stocks": [_public(screen_id, row) for row in matched],
            "sectors": sectors,
            "benchmark": _NIFTY["name"],
            "limitations": _limitations(screen_id),
        }
    )
    _CACHE[screen_id] = (time.time(), body)
    return body


def _measured_rows() -> tuple[list[dict], int]:
    global _BOARD
    if _BOARD and time.time() - _BOARD[0] < 180:
        return _BOARD[1], _BOARD[2]
    provider = quotes()
    benchmark = provider.get_candles(_NIFTY["yahoo"], "1d").get("candles") or []
    universe = broad_universe()

    def one(item):
        history = provider.get_candles(item.yahoo, "1d")
        measured = measure_symbol(history.get("candles") or [], benchmark)
        return item, history.get("error"), measured

    with ThreadPoolExecutor(max_workers=12) as pool:
        loaded = list(pool.map(one, universe))
    rows = []
    skipped = 0
    for item, error, measured in loaded:
        if measured is None:
            skipped += 1
            continue
        measured["symbol"] = item.symbol
        measured["company"] = item.name
        measured["sector"] = item.sector
        measured["fetch_error"] = error
        rows.append(measured)
    _BOARD = (time.time(), rows, skipped)
    return rows, skipped


def _intraday_inside_rows() -> tuple[list[dict], int]:
    cached = _CACHE.get("_inside_15m_rows")
    if cached and time.time() - cached[0] < 180:
        return cached[1]["rows"], cached[1]["skipped"]
    provider = quotes()
    universe = broad_universe()

    def one(item):
        history = provider.get_candles(item.yahoo, "15m")
        candles = history.get("candles") or []
        pattern = inside_bar_breakout(candles)
        if len(candles) < 3:
            return item, True, None
        row = {
            "symbol": item.symbol,
            "company": item.name,
            "sector": item.sector,
            "close": candles[-1]["close"],
            "bar_time": candles[-1].get("date"),
            "volume": candles[-1].get("volume") or 0,
            "fetch_error": history.get("error"),
            "inside_break": None if pattern is None else pattern["direction"],
            "mother_high": None if pattern is None else pattern["mother_high"],
            "mother_low": None if pattern is None else pattern["mother_low"],
            "break_pct": None if pattern is None else pattern["break_pct"],
        }
        return item, False, row

    with ThreadPoolExecutor(max_workers=12) as pool:
        loaded = list(pool.map(one, universe))
    rows = []
    skipped = 0
    for _item, missing, row in loaded:
        if missing or row is None:
            skipped += 1
            continue
        rows.append(row)
    _CACHE["_inside_15m_rows"] = (time.time(), {"rows": rows, "skipped": skipped})
    return rows, skipped


def _sort_key(screen_id: str, row: dict):
    if screen_id == "high_momentum":
        return row.get("distance_from_high_pct") if row.get("distance_from_high_pct") is not None else 99
    if screen_id == "volatility_contraction":
        return row.get("atr_contraction") if row.get("atr_contraction") is not None else 99
    if screen_id == "relative_strength":
        return -(row.get("excess_60") or 0)
    if screen_id == "gap":
        return -(abs(row.get("gap_pct") or 0))
    if screen_id == "volatility_breakout":
        return -(row.get("atr_expansion") or 0)
    if screen_id in {"inside_daily", "inside_15m"}:
        direction_rank = 0 if row.get("inside_break") == "up" else 1
        return (direction_rank, -(row.get("break_pct") or 0))
    if screen_id == "darvas":
        return row.get("distance_from_high_pct") if row.get("distance_from_high_pct") is not None else 99
    return row["symbol"]


def _public(screen_id: str, row: dict) -> dict:
    metrics = _metrics(screen_id, row)
    return {
        "symbol": row["symbol"],
        "company": row["company"],
        "sector": row["sector"],
        "price": row["close"],
        "bar_time": row.get("bar_time"),
        "metrics": metrics,
        "chart": f"/research?symbol={row['symbol']}",
    }


def _metrics(screen_id: str, row: dict) -> list[dict[str, str]]:
    if screen_id == "high_momentum":
        return [
            _pct("From 52w high", row.get("distance_from_high_pct")),
            _pct("Excess vs NIFTY 20d", row.get("excess_20")),
            {"label": "Relative volume", "value": _num(row.get("relative_volume"))},
        ]
    if screen_id == "volatility_contraction":
        return [
            {"label": "ATR contraction", "value": _num(row.get("atr_contraction"))},
            {"label": "Range", "value": "Narrower, then close through the 10-session high"},
        ]
    if screen_id == "relative_strength":
        return [
            _pct("Excess 20d", row.get("excess_20")),
            _pct("Excess 60d", row.get("excess_60")),
        ]
    if screen_id == "sector_rotation":
        return [
            {"label": "Sector", "value": row.get("sector") or "—"},
            _pct("Excess vs NIFTY 20d", row.get("excess_20")),
        ]
    if screen_id == "gap":
        return [
            {"label": "Setup", "value": row.get("gap_kind") or "—"},
            _pct("Opening gap", row.get("gap_pct")),
            {"label": "Volume", "value": f"{int(row.get('volume') or 0):,}"},
        ]
    if screen_id == "volatility_breakout":
        return [
            {"label": "ATR expansion", "value": _num(row.get("atr_expansion"))},
            {"label": "Direction", "value": (row.get("break_direction") or "—").capitalize()},
        ]
    if screen_id in {"inside_daily", "inside_15m"}:
        return [
            {"label": "Direction", "value": (row.get("inside_break") or "—").capitalize()},
            {"label": "Mother high", "value": _price(row.get("mother_high"))},
            {"label": "Mother low", "value": _price(row.get("mother_low"))},
            _pct("Beyond mother bar", row.get("break_pct")),
        ]
    if screen_id == "darvas":
        return [
            _pct("From 52w high", row.get("distance_from_high_pct")),
            _pct("Above 52w low", row.get("distance_from_low_pct")),
            {"label": "Volume", "value": f"{int(row.get('volume') or 0):,}"},
        ]
    return []


def _pct(label: str, value: float | None) -> dict[str, str]:
    if value is None:
        return {"label": label, "value": "—"}
    sign = "+" if value > 0 else ""
    return {"label": label, "value": f"{sign}{value:.2f}%"}


def _price(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.2f}"


def _num(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.2f}"


def _limitations(screen_id: str) -> list[str]:
    notes = [
        "The universe is the stored NIFTY 500 snapshot, covering large, mid, and small-cap index names rather than NIFTY 50 alone.",
    ]
    if screen_id == "inside_15m":
        notes.append(
            "15-minute bars are delayed and cover only a short recent window. During the session the latest bar may still be forming."
        )
    else:
        notes.append("Bars are the provider's delayed daily series. A match is a filter, not a forecast.")
    if screen_id in {"inside_daily", "inside_15m"}:
        notes.append(
            "The inside bar must sit strictly inside the prior bar. The latest close must clear the mother bar's high or low. A wick alone does not count."
        )
    if screen_id == "gap":
        notes.append("News is not attached. Continuation or reversal is judged from the daily bar, not a live intraday tape.")
    if screen_id == "sector_rotation":
        notes.append("Sector strength is the average excess return of snapshot names in that sector, not an official sector index.")
    if screen_id in {"high_momentum", "darvas"}:
        notes.append("The 52-week high and low use up to 252 prior sessions and exclude the latest bar.")
    return notes
