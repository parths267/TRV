"""Scanner, 52-week, and index studies on top of provider candles."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from app.market.analysis import (
    ScanRules,
    breadth,
    evaluate_scan,
    fifty_two_week,
    index_move,
    intraday_vwap,
    opening_gap,
    support_break,
)
from app.market.universe import BANKING_WATCH, BY_SYMBOL, INDICES, NIFTY_50, yahoo_for
from app.providers.registry import quotes
from app.services.board import banking_quotes, universe_board

_INDEX_BY_ID = {item["id"]: item for item in INDICES}


def _candles_for(symbol: str, interval: str, exchange: str = "NSE") -> dict:
    return quotes().get_candles(yahoo_for(symbol, exchange), interval)


def run_scanner(symbols: list[dict], rules: ScanRules, interval: str) -> dict:
    def one(item: dict) -> dict:
        history = _candles_for(item["symbol"], interval, item.get("exchange", "NSE"))
        result = evaluate_scan(history.get("candles") or [], rules, interval)
        result["symbol"] = item["symbol"]
        result["company"] = item.get("name")
        result["exchange"] = item.get("exchange", "NSE")
        result["fetch_error"] = history.get("error")
        result["provider"] = history.get("provider")
        result["adjusted"] = history.get("adjusted")
        result["chart"] = f"/research?symbol={item['symbol']}"
        if history.get("empty") or history.get("error"):
            result["qualified"] = False
            result["failed"] = result.get("failed") or []
            result["failed"].append(history.get("error") or "No candles returned.")
        return result

    with ThreadPoolExecutor(max_workers=6) as pool:
        rows = list(pool.map(one, symbols))
    hits = [row for row in rows if row.get("qualified")]
    return {
        "interval": interval,
        "rules": rules.__dict__,
        "scanned": len(rows),
        "qualified": hits,
        "rejected": len(rows) - len(hits),
        "example_only": (
            "A rule such as a 20-session close above the high with relative volume over 2 "
            "is a filter, not a claim that the stock will keep rising."
        ),
    }


def nifty_symbols() -> list[dict]:
    return [item.as_dict() for item in NIFTY_50]


def run_highs(approach_pct: float = 2.0) -> dict:
    def one(item) -> dict:
        history = _candles_for(item.symbol, "1d")
        study = fifty_two_week(history.get("candles") or [], approach_pct)
        study["symbol"] = item.symbol
        study["company"] = item.name
        study["fetch_error"] = history.get("error")
        study["provider"] = history.get("provider")
        study["chart"] = f"/research?symbol={item.symbol}"
        return study

    with ThreadPoolExecutor(max_workers=6) as pool:
        rows = list(pool.map(one, NIFTY_50))
    available = [row for row in rows if row.get("available")]

    def pick(flag: str) -> list[dict]:
        return [row for row in available if row.get(flag)]

    return {
        "method": "Prior 252 daily sessions, excluding the latest bar. Partial history is flagged.",
        "approach_pct": approach_pct,
        "new_closing_highs": pick("new_closing_high"),
        "new_intraday_highs": pick("new_intraday_high"),
        "new_closing_lows": pick("new_closing_low"),
        "new_intraday_lows": pick("new_intraday_low"),
        "approaching_highs": pick("approaching_high"),
        "approaching_lows": pick("approaching_low"),
        "unavailable": [row for row in rows if not row.get("available")],
    }


def run_index_monitor(threshold_pct: float = -0.6, window_minutes: int = 10) -> dict:
    """Example Bank NIFTY rule plus a reading for every configured index.

    The fast window uses 5-minute bars when the provider returns them. It does not
    downsample other intervals and does not invent the missing candles.
    """
    if window_minutes % 5 != 0 or window_minutes < 5:
        raise ValueError("window_minutes must be a positive multiple of 5")
    window_bars = window_minutes // 5
    provider = quotes()
    readings = []
    for item in INDICES:
        intraday = provider.get_candles(item["yahoo"], "5m")
        daily = provider.get_candles(item["yahoo"], "1d")
        move = index_move(
            intraday.get("candles") or [],
            threshold_pct=threshold_pct,
            window_bars=window_bars,
            bar_minutes=5,
        )
        daily_bars = daily.get("candles") or []
        gap = {"available": False, "reason": "Daily history missing."}
        vwap = None
        if len(daily_bars) >= 2:
            gap = opening_gap(daily_bars[-1]["open"], daily_bars[-2]["close"])
        if intraday.get("candles"):
            vwap_value = intraday_vwap(intraday["candles"])
            last = intraday["candles"][-1]["close"]
            vwap = {
                "value": None if vwap_value is None else round(vwap_value, 4),
                "last": last,
                "above": None if vwap_value is None else last > vwap_value,
                "note": "VWAP uses only the returned 5-minute bars and their volume.",
            }
        readings.append(
            {
                "id": item["id"],
                "name": item["name"],
                "tradingview": item["tradingview"],
                "intraday_error": intraday.get("error"),
                "intraday_count": intraday.get("count", 0),
                "move": move,
                "gap": gap,
                "vwap": vwap,
                "provider": intraday.get("provider"),
            }
        )

    banking = []
    breaks = 0
    unknown = 0
    for symbol in BANKING_WATCH:
        history = _candles_for(symbol, "1d")
        flag = support_break(history.get("candles") or [], 20)
        if flag is None:
            unknown += 1
        elif flag:
            breaks += 1
        banking.append({"symbol": symbol, "broke_prior_20_session_low": flag, "error": history.get("error")})

    board = universe_board()
    bank_changes = [row.get("change_pct") for row in banking_quotes()]
    bank_breadth = breadth(bank_changes)
    focus = next((row for row in readings if row["id"] == "banknifty"), None)
    example_triggered = bool(
        focus
        and focus["move"].get("triggered")
        and focus["move"].get("direction") == "down"
        and bank_breadth.get("deteriorating")
        and breaks >= 3
    )
    return {
        "example_rule": {
            "name": "banknifty_fast_drop",
            "statement": (
                "Alert only when Bank NIFTY's 5-minute window is at or below the threshold, "
                "large-bank breadth is deteriorating, and at least 3 watched banking names "
                "have closed below their prior 20-session daily low."
            ),
            "threshold_pct": threshold_pct,
            "window_minutes": window_minutes,
            "triggered": example_triggered,
            "is_prediction": False,
        },
        "indices": readings,
        "banking_support": {
            "names": banking,
            "breaks": breaks,
            "unknown": unknown,
            "universe_note": "Illustrative large banking names, not the official NIFTY Bank membership file.",
            "timeframe": "daily close versus prior 20 session lows",
        },
        "banking_breadth": bank_breadth,
        "nifty50_breadth": board["breadth"],
        "limitations": [
            "Constituent support is a daily calculation. It is supporting context, not evidence that those stocks broke support inside the same 10 minutes.",
            "No cause is assigned to the move.",
            "5-minute history is whatever the provider returned and may be delayed or empty.",
        ],
    }
