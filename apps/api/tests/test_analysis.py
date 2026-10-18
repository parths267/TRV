from datetime import datetime, timedelta, timezone

from app.market.analysis import (
    ScanRules,
    alert_allowed,
    evaluate_scan,
    fifty_two_week,
    index_move,
)
from app.market.costs import DEFAULT_COSTS


def _flat(n=60, price=100.0, volume=1_000_000):
    rows = []
    for i in range(n):
        rows.append(
            {
                "date": f"2024-06-{(i % 28) + 1:02d}",
                "open": price,
                "high": price + 1,
                "low": price - 1,
                "close": price,
                "volume": volume,
            }
        )
    return rows


def test_close_breakout_qualifies_and_a_touch_does_not():
    candles = _flat()
    candles[-1] = {**candles[-1], "open": 100, "high": 112, "low": 100, "close": 111, "volume": 3_000_000}
    rules = ScanRules(min_avg_traded_value=1_000)
    hit = evaluate_scan(candles, rules, "1d")
    assert hit["qualified"] is True
    assert hit["confirmation"] == "close_confirmed"
    assert hit["relative_volume"] == 3
    assert any("prior 20-session high" in line for line in hit["triggered"])

    touch = _flat()
    touch[-1] = {**touch[-1], "high": 112, "close": 100, "volume": 3_000_000}
    miss = evaluate_scan(touch, rules, "1d")
    assert miss["qualified"] is False


def test_fifty_two_week_uses_prior_sessions_only():
    candles = _flat(30, price=50)
    for i, row in enumerate(candles):
        row["high"] = 50
        row["low"] = 40
        row["close"] = 45
    candles[-1] = {**candles[-1], "high": 60, "low": 55, "close": 58, "volume": 5_000_000}
    study = fifty_two_week(candles, approach_pct=2)
    assert study["available"] is True
    assert study["partial_history"] is True
    assert study["sessions_used"] == 29
    assert study["new_closing_high"] is True
    assert study["reference_high"] == 50


def test_index_alert_respects_threshold():
    bars = [
        {"date": "t0", "open": 100, "high": 100, "low": 100, "close": 100, "volume": 1},
        {"date": "t1", "open": 100, "high": 100, "low": 99, "close": 99.8, "volume": 1},
        {"date": "t2", "open": 99.8, "high": 99.8, "low": 99, "close": 99.4, "volume": 1},
    ]
    quiet = index_move(bars, threshold_pct=-0.6, window_bars=1, bar_minutes=5)
    loud = index_move(bars, threshold_pct=-0.3, window_bars=1, bar_minutes=5)
    assert quiet["available"] is True
    assert quiet["triggered"] is False
    assert loud["triggered"] is True
    missing = index_move(bars[:1], threshold_pct=-0.6, window_bars=2, bar_minutes=5)
    assert missing["available"] is False
    assert missing["triggered"] is False


def test_alert_cooldown_and_rearm():
    now = datetime(2026, 10, 11, tzinfo=timezone.utc)
    assert alert_allowed("a", None, None, 3600, now) is True
    assert alert_allowed("a", "a", now - timedelta(seconds=10), 3600, now) is False
    assert alert_allowed("a", "a", now - timedelta(seconds=3600), 3600, now) is True
    assert alert_allowed("b", "a", now - timedelta(seconds=10), 3600, now) is True
    naive = (now - timedelta(seconds=10)).replace(tzinfo=None)
    assert alert_allowed("a", "a", naive, 3600, now) is False


def test_indian_cost_round_trip_is_allocated_across_both_sides():
    detail = DEFAULT_COSTS.breakdown()
    assert detail["round_trip_pct"] > 0
    assert abs(detail["engine_commission_pct_per_side"] * 2 - detail["round_trip_pct"]) < 1e-4
    buy = DEFAULT_COSTS.fees_inr("buy", 100_000)
    sell = DEFAULT_COSTS.fees_inr("sell", 100_000)
    assert sell > buy
