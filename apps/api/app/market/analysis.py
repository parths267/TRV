"""Deterministic scanners. Indicators come from the tradingview-mcp engine.

Signals use only bars up to and including the latest closed bar that was supplied.
The caller decides whether that bar is a confirmed close or a still-forming candle.
Missing bars are not invented.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
from typing import Any

from tradingview_mcp.core.services.indicators_calc import (
    calc_atr,
    calc_ema,
    calc_macd,
    calc_rsi,
    calc_sma,
    calc_supertrend,
)

# Trading sessions, not calendar days. 252 is the usual Indian cash-market year.
FIFTY_TWO_WEEK_SESSIONS = 252


@dataclass
class ScanRules:
    direction: str = "breakout"
    lookback: int = 20
    min_relative_volume: float = 2.0
    min_avg_traded_value: float = 50_000_000
    require_above_sma: int | None = 50
    require_close_through: bool = True
    rsi_min: float | None = None
    rsi_max: float | None = None
    require_macd_histogram_positive: bool = False
    min_price: float | None = None
    max_price: float | None = None

    @classmethod
    def from_dict(cls, raw: dict | None) -> "ScanRules":
        raw = raw or {}
        known = {field: raw[field] for field in cls.__dataclass_fields__ if field in raw}
        rules = cls(**known)
        if rules.direction not in {"breakout", "breakdown"}:
            raise ValueError("direction must be breakout or breakdown")
        if rules.lookback < 2 or rules.lookback > 250:
            raise ValueError("lookback must be between 2 and 250")
        if rules.min_relative_volume < 0:
            raise ValueError("min_relative_volume cannot be negative")
        return rules


def _window(candles: list[dict], lookback: int) -> list[dict] | None:
    if len(candles) < lookback + 1:
        return None
    return candles[-(lookback + 1) : -1]


def _relative_volume(candles: list[dict], lookback: int) -> float | None:
    prior = _window(candles, lookback)
    if not prior:
        return None
    baseline = [c.get("volume") or 0 for c in prior]
    avg = sum(baseline) / len(baseline)
    if avg <= 0:
        return None
    return (candles[-1].get("volume") or 0) / avg


def _avg_traded_value(candles: list[dict], lookback: int) -> float | None:
    prior = _window(candles, lookback)
    if not prior:
        return None
    values = [(c["close"] * (c.get("volume") or 0)) for c in prior]
    return sum(values) / len(values)


def evaluate_scan(candles: list[dict], rules: ScanRules, timeframe: str = "1d") -> dict:
    """Return a result even when the symbol does not qualify, so the UI can explain why."""
    bar = candles[-1] if candles else None
    base: dict[str, Any] = {
        "qualified": False,
        "timeframe": timeframe,
        "direction": rules.direction,
        "confirmation": None,
        "triggered": [],
        "failed": [],
        "invalidation": None,
        "indicators": {},
        "limitations": [],
    }
    if bar is None:
        base["failed"].append("No candles were returned.")
        return base
    prior = _window(candles, rules.lookback)
    if prior is None:
        base["failed"].append(
            f"Need at least {rules.lookback + 1} bars; received {len(candles)}. No bars were filled in."
        )
        return base

    level = max(c["high"] for c in prior) if rules.direction == "breakout" else min(c["low"] for c in prior)
    close = bar["close"]
    high = bar["high"]
    low = bar["low"]
    rel = _relative_volume(candles, rules.lookback)
    traded = _avg_traded_value(candles, rules.lookback)
    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]

    sma = None
    if rules.require_above_sma:
        sma_series = calc_sma(closes, rules.require_above_sma)
        sma = sma_series[-1]
    rsi_series = calc_rsi(closes, 14)
    macd = calc_macd(closes)
    atr = calc_atr(highs, lows, closes, 14)
    supertrend = calc_supertrend(highs, lows, closes)

    crossed = close > level if rules.direction == "breakout" else close < level
    touched = high > level if rules.direction == "breakout" else low < level
    if rules.require_close_through:
        confirmed = crossed
        confirmation = "close_confirmed" if crossed else None
    else:
        confirmed = touched
        confirmation = "close_confirmed" if crossed else ("intrabar_only" if touched else None)

    if confirmed and confirmation:
        base["triggered"].append(
            f"Price {'closed' if confirmation == 'close_confirmed' else 'traded'} "
            f"{'above' if rules.direction == 'breakout' else 'below'} the prior {rules.lookback}-session "
            f"{'high' if rules.direction == 'breakout' else 'low'} of {level:.4f}."
        )
    else:
        base["failed"].append(
            f"Latest bar did not clear the prior {rules.lookback}-session "
            f"{'high' if rules.direction == 'breakout' else 'low'} ({level:.4f})."
        )

    if rel is None:
        base["failed"].append("Relative volume is unavailable because the baseline volume is zero or missing.")
    elif rel + 1e-9 >= rules.min_relative_volume:
        base["triggered"].append(f"Relative volume {rel:.2f} vs the prior {rules.lookback} sessions.")
    else:
        base["failed"].append(
            f"Relative volume {rel:.2f} is below the required {rules.min_relative_volume:.2f}."
        )

    if traded is None:
        base["failed"].append("Average traded value is unavailable.")
    elif traded + 1e-6 >= rules.min_avg_traded_value:
        base["triggered"].append(f"Average traded value {traded:.0f} meets the liquidity filter.")
    else:
        base["failed"].append(
            f"Average traded value {traded:.0f} is below {rules.min_avg_traded_value:.0f}."
        )

    if rules.require_above_sma:
        if sma is None:
            base["failed"].append(f"SMA{rules.require_above_sma} is not ready.")
        elif (close > sma) if rules.direction == "breakout" else (close < sma):
            base["triggered"].append(f"Close is on the required side of SMA{rules.require_above_sma} ({sma:.4f}).")
        else:
            base["failed"].append(f"Close is not on the required side of SMA{rules.require_above_sma} ({sma:.4f}).")

    rsi = rsi_series[-1]
    if rules.rsi_min is not None or rules.rsi_max is not None:
        if rsi is None:
            base["failed"].append("RSI is not ready.")
        elif (rules.rsi_min is None or rsi >= rules.rsi_min) and (rules.rsi_max is None or rsi <= rules.rsi_max):
            base["triggered"].append(f"RSI {rsi:.2f} is inside the configured band.")
        else:
            base["failed"].append(f"RSI {rsi:.2f} is outside the configured band.")

    histogram = macd["histogram"][-1]
    if rules.require_macd_histogram_positive:
        if histogram is None:
            base["failed"].append("MACD histogram is not ready.")
        elif (histogram > 0) if rules.direction == "breakout" else (histogram < 0):
            base["triggered"].append(f"MACD histogram {histogram:.4f} confirms the direction.")
        else:
            base["failed"].append(f"MACD histogram {histogram:.4f} does not confirm the direction.")

    if rules.min_price is not None and close < rules.min_price:
        base["failed"].append(f"Price {close:.4f} is below the minimum {rules.min_price:.4f}.")
    if rules.max_price is not None and close > rules.max_price:
        base["failed"].append(f"Price {close:.4f} is above the maximum {rules.max_price:.4f}.")

    price_ok = (rules.min_price is None or close >= rules.min_price) and (
        rules.max_price is None or close <= rules.max_price
    )
    volume_ok = rel is not None and rel + 1e-9 >= rules.min_relative_volume
    liquidity_ok = traded is not None and traded + 1e-6 >= rules.min_avg_traded_value
    trend_ok = True
    if rules.require_above_sma:
        trend_ok = sma is not None and ((close > sma) if rules.direction == "breakout" else (close < sma))
    rsi_ok = True
    if rules.rsi_min is not None or rules.rsi_max is not None:
        rsi_ok = rsi is not None and (rules.rsi_min is None or rsi >= rules.rsi_min) and (
            rules.rsi_max is None or rsi <= rules.rsi_max
        )
    macd_ok = True
    if rules.require_macd_histogram_positive:
        macd_ok = histogram is not None and (
            (histogram > 0) if rules.direction == "breakout" else (histogram < 0)
        )

    qualified = bool(confirmed and volume_ok and liquidity_ok and trend_ok and rsi_ok and macd_ok and price_ok)
    if timeframe != "1d" and confirmation == "close_confirmed":
        base["limitations"].append(
            "Intraday 'close confirmed' means the latest returned candle closed, not that the session has ended."
        )
    if timeframe == "1d":
        base["limitations"].append("Daily signals are confirmed only for the latest completed daily bar supplied by the provider.")

    base.update(
        {
            "qualified": qualified,
            "confirmation": confirmation if qualified or confirmed else None,
            "level": level,
            "close": close,
            "relative_volume": None if rel is None else round(rel, 4),
            "avg_traded_value": None if traded is None else round(traded, 2),
            "bar_time": bar.get("date"),
            "invalidation": (
                f"A later close back {'below' if rules.direction == 'breakout' else 'above'} {level:.4f} "
                "invalidates this signal."
            ),
            "indicators": {
                "sma": None if sma is None else round(sma, 4),
                "rsi": None if rsi is None else round(rsi, 2),
                "macd_histogram": None if histogram is None else round(histogram, 4),
                "atr": None if atr[-1] is None else round(atr[-1], 4),
                "supertrend": supertrend["direction"][-1],
                "ema20": _last(calc_ema(closes, 20)),
            },
        }
    )
    return base


def _last(series: list) -> float | None:
    value = series[-1] if series else None
    return None if value is None else round(value, 4)


def fifty_two_week(candles: list[dict], approach_pct: float = 2.0) -> dict:
    """52-week style distance using up to 252 prior daily sessions, excluding the latest bar.

    The latest bar is compared with that history so today's high is not part of its own reference.
    If fewer than 252 prior sessions exist, the actual count is reported and the result is partial.
    """
    if len(candles) < 21:
        return {
            "available": False,
            "reason": f"Need at least 21 daily bars to rank a range; received {len(candles)}.",
        }
    current = candles[-1]
    history = candles[:-1][-FIFTY_TWO_WEEK_SESSIONS:]
    sessions = len(history)
    ref_high = max(c["high"] for c in history)
    ref_low = min(c["low"] for c in history)
    close = current["close"]
    if ref_high <= 0 or ref_low <= 0:
        return {"available": False, "reason": "Reference high or low is not a positive price."}

    dist_high = (ref_high - close) / ref_high * 100
    dist_low = (close - ref_low) / ref_low * 100
    closing_high = close > ref_high
    intraday_high = current["high"] > ref_high and not closing_high
    closing_low = close < ref_low
    intraday_low = current["low"] < ref_low and not closing_low
    rel = _relative_volume(candles, min(20, sessions))
    prior20 = history[-20:]
    span = (max(c["high"] for c in prior20) - min(c["low"] for c in prior20)) / close * 100 if close else None
    return {
        "available": True,
        "method": "max high / min low of prior daily sessions, excluding the latest bar",
        "sessions_used": sessions,
        "sessions_requested": FIFTY_TWO_WEEK_SESSIONS,
        "partial_history": sessions < FIFTY_TWO_WEEK_SESSIONS,
        "reference_high": round(ref_high, 4),
        "reference_low": round(ref_low, 4),
        "close": close,
        "distance_from_high_pct": round(dist_high, 2),
        "distance_from_low_pct": round(dist_low, 2),
        "new_closing_high": closing_high,
        "new_intraday_high": intraday_high,
        "new_closing_low": closing_low,
        "new_intraday_low": intraday_low,
        "approaching_high": (not closing_high and not intraday_high and 0 <= dist_high <= approach_pct),
        "approaching_low": (not closing_low and not intraday_low and 0 <= dist_low <= approach_pct),
        "volume_confirmed": rel is not None and rel >= 1.5,
        "relative_volume": None if rel is None else round(rel, 4),
        "tight_range_before_high": bool(span is not None and span <= 8 and (closing_high or intraday_high)),
        "range_20_pct": None if span is None else round(span, 2),
        "bar_time": current.get("date"),
        "corporate_actions": (
            "History uses the provider's adjusted daily bars when adjustment is present. "
            "Unadjusted gaps from splits can still distort the range."
        ),
    }


def window_return(bars: list[dict], bars_back: int) -> dict | None:
    """Percent change from the close `bars_back` ago to the latest close. No filled gaps."""
    if bars_back < 1 or len(bars) < bars_back + 1:
        return None
    start = bars[-(bars_back + 1)]["close"]
    end = bars[-1]["close"]
    if not start:
        return None
    return {
        "from": bars[-(bars_back + 1)].get("date"),
        "to": bars[-1].get("date"),
        "start": start,
        "end": end,
        "change_pct": round((end - start) / start * 100, 4),
        "bars": bars_back,
    }


def intraday_vwap(bars: list[dict]) -> float | None:
    """Session VWAP from the bars provided. Returns None when volume is missing."""
    pv = 0.0
    vol = 0.0
    for bar in bars:
        volume = bar.get("volume") or 0
        if volume <= 0:
            continue
        typical = (bar["high"] + bar["low"] + bar["close"]) / 3
        pv += typical * volume
        vol += volume
    if vol <= 0:
        return None
    return pv / vol


def breadth(changes: list[float | None]) -> dict:
    known = [c for c in changes if c is not None]
    advances = sum(1 for c in known if c > 0)
    declines = sum(1 for c in known if c < 0)
    unchanged = sum(1 for c in known if c == 0)
    ratio = None if not known else round(advances / len(known), 4)
    return {
        "sample": len(known),
        "missing": len(changes) - len(known),
        "advances": advances,
        "declines": declines,
        "unchanged": unchanged,
        "advance_ratio": ratio,
        "deteriorating": bool(ratio is not None and ratio < 0.4 and len(known) >= 5),
        "improving": bool(ratio is not None and ratio > 0.6 and len(known) >= 5),
    }


def index_move(
    bars: list[dict],
    *,
    threshold_pct: float,
    window_bars: int,
    bar_minutes: int | None,
) -> dict:
    """Fire only when the measured window breaches the threshold.

    A negative threshold alerts on a drop at least that large. A positive threshold
    alerts on a rise at least that large. Zero is rejected by the caller.
    """
    measured = window_return(bars, window_bars)
    if measured is None:
        return {
            "triggered": False,
            "available": False,
            "reason": (
                f"Need {window_bars + 1} bars to measure this window; received {len(bars)}. "
                "The move was not estimated."
            ),
        }
    change = measured["change_pct"]
    if threshold_pct < 0:
        triggered = change <= threshold_pct
        direction = "down"
    else:
        triggered = change >= threshold_pct
        direction = "up"
    return {
        "triggered": triggered,
        "available": True,
        "direction": direction,
        "threshold_pct": threshold_pct,
        "change_pct": change,
        "window_bars": window_bars,
        "bar_minutes": bar_minutes,
        "window_minutes": None if not bar_minutes else window_bars * bar_minutes,
        "from": measured["from"],
        "to": measured["to"],
        "confirmation": "developing" if bar_minutes else "daily_close",
        "invalidation": "The window resets as new bars arrive; this is a measured move, not a forecast.",
    }


def support_break(candles: list[dict], lookback: int = 20) -> bool | None:
    prior = _window(candles, lookback)
    if prior is None:
        return None
    return candles[-1]["close"] < min(c["low"] for c in prior)


def opening_gap(today_open: float | None, previous_close: float | None, threshold_pct: float = 0.5) -> dict:
    if not today_open or not previous_close:
        return {"available": False, "reason": "Open or previous close is missing."}
    gap = (today_open - previous_close) / previous_close * 100
    return {
        "available": True,
        "gap_pct": round(gap, 4),
        "large": abs(gap) >= threshold_pct,
        "threshold_pct": threshold_pct,
    }


def alert_allowed(
    fingerprint: str,
    last_fingerprint: str | None,
    last_triggered_at,
    cooldown_seconds: int,
    now,
) -> bool:
    """Same fingerprint stays silent until the cooldown ends. A new fingerprint re-arms immediately."""
    if not last_fingerprint or last_fingerprint != fingerprint or last_triggered_at is None:
        return True
    previous = last_triggered_at
    current = now
    if previous.tzinfo is None:
        previous = previous.replace(tzinfo=timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    elapsed = (current - previous).total_seconds()
    return elapsed >= cooldown_seconds
