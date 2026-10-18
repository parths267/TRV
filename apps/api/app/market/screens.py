"""Price-based strategy screens. Rules use supplied bars only.

Screens that need FII holdings, financial ratios, or an event calendar are
listed so the product can name them, and they return no stocks.
"""
from __future__ import annotations

from typing import Any

from tradingview_mcp.core.services.indicators_calc import calc_atr

from app.market.analysis import fifty_two_week

CATALOG: tuple[dict[str, str], ...] = (
    {
        "id": "high_momentum",
        "title": "52-week high momentum",
        "summary": "Stocks near or breaking annual highs",
        "rule": "Within 10% of the prior 52-week high, or through it, with 20-session relative strength above NIFTY 50 and relative volume of at least 1.2.",
        "status": "ready",
    },
    {
        "id": "volatility_contraction",
        "title": "Volatility contraction",
        "summary": "Tightening price ranges before possible expansion",
        "rule": "The 10 sessions before the latest bar are narrower than the 10 before them, ATR has contracted, and the latest close breaks that tight range.",
        "status": "ready",
    },
    {
        "id": "relative_strength",
        "title": "Relative strength vs. NIFTY 50",
        "summary": "Stocks outperforming the broader market",
        "rule": "Stock return minus NIFTY 50 return is positive over both the last 20 and 60 shared sessions.",
        "status": "ready",
    },
    {
        "id": "sector_rotation",
        "title": "Sector rotation",
        "summary": "Capital moving toward stronger sectors",
        "rule": "Sectors ranked by average 20-session excess return versus NIFTY 50. Matches are names in the top three sectors that are themselves ahead of the index.",
        "status": "ready",
    },
    {
        "id": "gap",
        "title": "Gap-and-go / gap reversal",
        "summary": "Large opening gaps that continue or reverse",
        "rule": "Opening gap of at least 1% versus the prior close, latest volume above 100,000, and the daily close either holds the gap or crosses back through the prior close.",
        "status": "ready",
    },
    {
        "id": "event",
        "title": "Event-driven screening",
        "summary": "Price and volume behaviour around results, deals, or corporate actions",
        "rule": "Needs an event calendar plus abnormal return and volume. No event list is inferred from price alone.",
        "status": "unavailable",
    },
    {
        "id": "volatility_breakout",
        "title": "Volatility breakout",
        "summary": "Large move after a quiet period",
        "rule": "ATR is at least 25% above its reading 10 sessions ago, that earlier reading was quieter than the one before it, and the close breaks the prior 20-session high or low.",
        "status": "ready",
    },
    {
        "id": "inside_daily",
        "title": "Inside bar breakout · daily",
        "summary": "Daily close through the mother bar after an inside day",
        "rule": "The previous daily bar sits strictly inside the bar before it. The latest daily close is above that mother bar's high or below its low.",
        "status": "ready",
    },
    {
        "id": "inside_15m",
        "title": "Inside bar breakout · 15 minute",
        "summary": "15-minute close through the mother bar after an inside bar",
        "rule": "The previous 15-minute bar sits strictly inside the bar before it. The latest 15-minute close is above that mother bar's high or below its low.",
        "status": "ready",
    },
    {
        "id": "fii",
        "title": "FII buying",
        "summary": "Stocks purchased continuously by FIIs",
        "rule": "Needs shareholding disclosures that show repeated FII buying. A price feed cannot show who bought.",
        "status": "unavailable",
    },
    {
        "id": "darvas",
        "title": "Darvas scan",
        "summary": "Near the annual high, well off the annual low, liquid, and above ₹10",
        "rule": "Within 10% of the prior 52-week high, at least 100% above the prior 52-week low, latest volume above 100,000, and price above 10.",
        "status": "ready",
    },
    {
        "id": "value",
        "title": "Value stocks",
        "summary": "High operating margin and ROCE, low debt to equity",
        "rule": "Needs operating margin, ROCE, and debt-to-equity. Those ratios are not in the price feed.",
        "status": "unavailable",
    },
)

BY_ID = {item["id"]: item for item in CATALOG}

UNAVAILABLE_REASON = {
    "event": (
        "The exchange disclosure client does not return a results, bulk, or block calendar from here. "
        "Stocks are not labeled event-driven without that calendar."
    ),
    "fii": (
        "Continuous FII buying is a shareholding record. This app has no FII feed, so the list is empty."
    ),
    "value": (
        "Operating margin, ROCE, and debt-to-equity are not in the quote feed. "
        "The list stays empty until a fundamentals source is connected."
    ),
}


def _span(bars: list[dict]) -> float | None:
    if not bars:
        return None
    return max(bar["high"] for bar in bars) - min(bar["low"] for bar in bars)


def _atr(candles: list[dict]) -> list[float | None]:
    return calc_atr(
        [bar["high"] for bar in candles],
        [bar["low"] for bar in candles],
        [bar["close"] for bar in candles],
        14,
    )


def _at(series: list[float | None], index: int) -> float | None:
    if not series:
        return None
    try:
        value = series[index]
    except IndexError:
        return None
    return None if value is None else float(value)


def excess_return(stock: list[dict], benchmark: list[dict], bars_back: int) -> float | None:
    """Stock percent change minus benchmark percent change over shared session dates."""
    if bars_back < 1:
        return None
    stock_close = {str(bar.get("date", ""))[:10]: bar["close"] for bar in stock}
    bench_close = {str(bar.get("date", ""))[:10]: bar["close"] for bar in benchmark}
    common = [day for day in stock_close if day in bench_close]
    if len(common) < bars_back + 1:
        return None
    start, end = common[-(bars_back + 1)], common[-1]
    stock_start, stock_end = stock_close[start], stock_close[end]
    bench_start, bench_end = bench_close[start], bench_close[end]
    if not stock_start or not bench_start:
        return None
    stock_pct = (stock_end - stock_start) / stock_start * 100
    bench_pct = (bench_end - bench_start) / bench_start * 100
    return round(stock_pct - bench_pct, 2)


def inside_bar_breakout(candles: list[dict]) -> dict[str, Any] | None:
    """Latest close through the mother bar after a strictly inside prior bar.

    The mother bar is two bars back. The inside bar is the one before the latest.
    Equal highs or lows do not count as inside, and a wick without a closing
    break does not count as a breakout.
    """
    if len(candles) < 3:
        return None
    mother, inside, signal = candles[-3], candles[-2], candles[-1]
    if inside["high"] >= mother["high"] or inside["low"] <= mother["low"]:
        return None
    close = signal["close"]
    if close > mother["high"]:
        direction = "up"
        distance = (close - mother["high"]) / mother["high"] * 100 if mother["high"] else None
    elif close < mother["low"]:
        direction = "down"
        distance = (mother["low"] - close) / mother["low"] * 100 if mother["low"] else None
    else:
        return None
    return {
        "direction": direction,
        "close": close,
        "bar_time": signal.get("date"),
        "mother_high": round(mother["high"], 4),
        "mother_low": round(mother["low"], 4),
        "break_pct": None if distance is None else round(distance, 2),
        "volume": signal.get("volume") or 0,
    }


def measure_symbol(candles: list[dict], benchmark: list[dict]) -> dict[str, Any] | None:
    if len(candles) < 21:
        return None
    latest = candles[-1]
    study = fifty_two_week(candles)
    atr = _atr(candles)
    atr_now = _at(atr, -1)
    atr_10 = _at(atr, -11)
    atr_20 = _at(atr, -21)
    atr_yesterday = _at(atr, -2)
    atr_before_tight = _at(atr, -12)
    prior_10 = candles[-11:-1]
    prior_10_before = candles[-21:-11]
    span_10 = _span(prior_10)
    span_before = _span(prior_10_before)
    prior_20 = candles[-21:-1] if len(candles) >= 22 else None
    close = latest["close"]
    gap_pct = None
    gap_kind = None
    if len(candles) >= 2 and candles[-2]["close"]:
        gap_pct = round((latest["open"] - candles[-2]["close"]) / candles[-2]["close"] * 100, 2)
        held = (gap_pct > 0 and close >= candles[-2]["close"]) or (gap_pct < 0 and close <= candles[-2]["close"])
        crossed = (gap_pct > 0 and close < candles[-2]["close"]) or (gap_pct < 0 and close > candles[-2]["close"])
        if abs(gap_pct) >= 1 and (latest.get("volume") or 0) > 100_000:
            if crossed:
                gap_kind = "Gap reversal"
            elif held and ((gap_pct > 0 and close > latest["open"]) or (gap_pct < 0 and close < latest["open"])):
                gap_kind = "Gap and go"
    direction = None
    if prior_20:
        if close > max(bar["high"] for bar in prior_20):
            direction = "up"
        elif close < min(bar["low"] for bar in prior_20):
            direction = "down"
    rel = None
    baseline = [bar.get("volume") or 0 for bar in prior_10]
    avg_volume = sum(baseline) / len(baseline) if baseline else 0
    if avg_volume > 0:
        rel = round((latest.get("volume") or 0) / avg_volume, 2)
    inside = inside_bar_breakout(candles)
    return {
        "close": close,
        "volume": latest.get("volume") or 0,
        "bar_time": latest.get("date"),
        "distance_from_high_pct": study.get("distance_from_high_pct") if study.get("available") else None,
        "distance_from_low_pct": study.get("distance_from_low_pct") if study.get("available") else None,
        "new_high": bool(study.get("available") and (study.get("new_closing_high") or study.get("new_intraday_high"))),
        "relative_volume": rel,
        "excess_20": excess_return(candles, benchmark, 20),
        "excess_60": excess_return(candles, benchmark, 60),
        "ranges_narrowed": bool(span_10 is not None and span_before is not None and span_10 < span_before),
        "atr_contraction": (
            None
            if not atr_yesterday or not atr_before_tight
            else round(atr_yesterday / atr_before_tight, 2)
        ),
        "broke_tight_high": bool(prior_10 and close > max(bar["high"] for bar in prior_10)),
        "gap_pct": gap_pct,
        "gap_kind": gap_kind,
        "atr_expansion": None if not atr_now or not atr_10 else round(atr_now / atr_10, 2),
        "quiet_before": bool(atr_10 and atr_20 and atr_10 <= atr_20),
        "break_direction": direction,
        "inside_break": None if inside is None else inside["direction"],
        "mother_high": None if inside is None else inside["mother_high"],
        "mother_low": None if inside is None else inside["mother_low"],
        "break_pct": None if inside is None else inside["break_pct"],
    }


def qualifies(screen_id: str, row: dict[str, Any]) -> bool:
    if screen_id == "high_momentum":
        near = row.get("new_high") or (
            row.get("distance_from_high_pct") is not None and 0 <= row["distance_from_high_pct"] <= 10
        )
        return bool(near and (row.get("relative_volume") or 0) >= 1.2 and (row.get("excess_20") or 0) > 0)
    if screen_id == "volatility_contraction":
        ratio = row.get("atr_contraction")
        return bool(row.get("ranges_narrowed") and ratio is not None and ratio <= 0.85 and row.get("broke_tight_high"))
    if screen_id == "relative_strength":
        return (row.get("excess_20") or 0) > 0 and (row.get("excess_60") or 0) > 0
    if screen_id == "gap":
        return row.get("gap_kind") in {"Gap and go", "Gap reversal"}
    if screen_id == "volatility_breakout":
        expansion = row.get("atr_expansion")
        return bool(expansion is not None and expansion >= 1.25 and row.get("quiet_before") and row.get("break_direction"))
    if screen_id in {"inside_daily", "inside_15m"}:
        return row.get("inside_break") in {"up", "down"}
    if screen_id == "darvas":
        high = row.get("distance_from_high_pct")
        low = row.get("distance_from_low_pct")
        near_high = row.get("new_high") or (high is not None and high <= 10)
        return bool(near_high and low is not None and low >= 100 and row.get("volume", 0) > 100_000 and row.get("close", 0) > 10)
    return False


def sector_leaders(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Rank sectors by mean 20-session excess return, then keep names in the top three rising sectors."""
    grouped: dict[str, list[float]] = {}
    for row in rows:
        excess = row.get("excess_20")
        sector = row.get("sector")
        if excess is None or not sector:
            continue
        grouped.setdefault(sector, []).append(excess)
    ranks = []
    for sector, values in grouped.items():
        ranks.append(
            {
                "sector": sector,
                "excess_20_pct": round(sum(values) / len(values), 2),
                "count": len(values),
            }
        )
    ranks.sort(key=lambda item: item["excess_20_pct"], reverse=True)
    for index, item in enumerate(ranks, start=1):
        item["rank"] = index
    leading = {item["sector"] for item in ranks[:3] if item["excess_20_pct"] > 0}
    matched = [
        row
        for row in rows
        if row.get("sector") in leading and (row.get("excess_20") or 0) > 0
    ]
    matched.sort(key=lambda row: row.get("excess_20") or 0, reverse=True)
    return matched, ranks
