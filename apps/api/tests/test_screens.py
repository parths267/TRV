from datetime import datetime, timedelta

from app.market.screens import excess_return, inside_bar_breakout, measure_symbol, qualifies, sector_leaders


def _series(n: int, start: float, step: float = 0.0, volume: int = 200_000, last: dict | None = None):
    rows = []
    price = start
    for i in range(n):
        close = price + step
        bar = {
            "date": (datetime(2024, 1, 1) + timedelta(days=i)).strftime("%Y-%m-%d"),
            "open": price,
            "high": max(price, close) + 0.4,
            "low": min(price, close) - 0.4,
            "close": close,
            "volume": volume,
        }
        price = close
        rows.append(bar)
    if last:
        rows[-1].update(last)
        rows[-1]["high"] = max(rows[-1]["open"], rows[-1]["close"], rows[-1].get("high", rows[-1]["close"]))
        rows[-1]["low"] = min(rows[-1]["open"], rows[-1]["close"], rows[-1].get("low", rows[-1]["close"]))
    return rows


def test_darvas_requires_location_volume_and_price():
    climb = _series(260, 40, step=0.3, volume=250_000)
    climb[-1]["close"] = climb[-2]["high"] * 0.96
    climb[-1]["open"] = climb[-1]["close"]
    climb[-1]["high"] = climb[-1]["close"] + 0.2
    climb[-1]["low"] = climb[-1]["close"] - 0.2
    row = measure_symbol(climb, climb)
    assert row is not None
    assert qualifies("darvas", row)

    quiet = _series(260, 40, step=0.3, volume=1_000)
    quiet[-1]["close"] = quiet[-2]["high"] * 0.96
    assert not qualifies("darvas", measure_symbol(quiet, quiet))


def test_gap_go_and_reversal_are_distinct():
    base = _series(40, 100, volume=250_000)
    go = [dict(bar) for bar in base]
    go[-1].update(open=102, high=104, low=101.5, close=103, volume=250_000)
    reversal = [dict(bar) for bar in base]
    reversal[-1].update(open=102, high=102.4, low=98.5, close=99, volume=250_000)
    assert measure_symbol(go, go)["gap_kind"] == "Gap and go"
    assert measure_symbol(reversal, reversal)["gap_kind"] == "Gap reversal"
    assert qualifies("gap", measure_symbol(go, go))
    small = [dict(bar) for bar in base]
    small[-1].update(open=100.2, high=100.4, low=99.8, close=100.3, volume=250_000)
    assert not qualifies("gap", measure_symbol(small, small))


def test_relative_strength_needs_both_windows_ahead_of_nifty():
    stock = _series(80, 100, step=0.4)
    bench = _series(80, 100, step=0)
    row = measure_symbol(stock, bench)
    assert row["excess_20"] > 0
    assert row["excess_60"] > 0
    assert qualifies("relative_strength", row)
    assert excess_return(bench, stock, 20) < 0
    assert not qualifies("relative_strength", measure_symbol(bench, stock))


def test_sector_rotation_keeps_names_in_the_leading_sectors():
    rows = [
        {"symbol": "AAA", "sector": "Energy", "excess_20": 4},
        {"symbol": "BBB", "sector": "Energy", "excess_20": 2},
        {"symbol": "CCC", "sector": "Healthcare", "excess_20": 1},
        {"symbol": "DDD", "sector": "Materials", "excess_20": -3},
        {"symbol": "EEE", "sector": "Materials", "excess_20": 0.2},
    ]
    matched, ranks = sector_leaders(rows)
    assert ranks[0]["sector"] == "Energy"
    assert {row["symbol"] for row in matched} == {"AAA", "BBB", "CCC"}


def _bar(high, low, close, open_=None):
    return {"date": "2024-01-01", "open": close if open_ is None else open_, "high": high, "low": low, "close": close, "volume": 1000}


def test_inside_bar_breakout_needs_a_strict_inside_bar_and_a_closing_break():
    mother = _bar(110, 90, 100)
    inside = _bar(105, 95, 101)
    up = inside_bar_breakout([mother, inside, _bar(112, 100, 111)])
    down = inside_bar_breakout([mother, inside, _bar(100, 88, 89)])
    assert up["direction"] == "up"
    assert down["direction"] == "down"
    assert inside_bar_breakout([mother, inside, _bar(109, 96, 104)]) is None
    assert inside_bar_breakout([mother, _bar(110, 95, 100), _bar(112, 100, 111)]) is None
    assert qualifies("inside_daily", {"inside_break": "up"})
    assert qualifies("inside_15m", {"inside_break": "down"})
    assert not qualifies("inside_daily", {"inside_break": None})


def test_contraction_and_breakout_rules_are_explicit():
    assert qualifies(
        "volatility_contraction",
        {"ranges_narrowed": True, "atr_contraction": 0.7, "broke_tight_high": True},
    )
    assert not qualifies(
        "volatility_contraction",
        {"ranges_narrowed": True, "atr_contraction": 0.7, "broke_tight_high": False},
    )
    assert qualifies(
        "volatility_breakout",
        {"atr_expansion": 1.4, "quiet_before": True, "break_direction": "up"},
    )
    assert not qualifies(
        "volatility_breakout",
        {"atr_expansion": 1.4, "quiet_before": False, "break_direction": "up"},
    )
