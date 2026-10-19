import datetime as dt
from zoneinfo import ZoneInfo

from app.autotrader.engine import CFG, Bar, Engine, Leg, Quote, charges, rsi
from app.autotrader.upstox_feed import choose_underlying, to_bars

IST = ZoneInfo("Asia/Kolkata")


class FakeFeed:
    symbol = "NIFTY"
    expiry = "2026-10-20"
    exchange = "NSE"
    step = 50
    lot_size = 65

    def __init__(self, chain, now, bars=None):
        self._chain = chain
        self._now = now
        self._bars = bars or []

    def chain(self):
        return self._chain

    def now(self):
        return self._now

    def spot(self):
        return 23000.0

    def bars(self, tf):
        return self._bars

    def stop_requested(self):
        return False


def _quote(bid, ask, delta=0.2):
    return Quote(bid=bid, ask=ask, ltp=(bid + ask) / 2, oi=100000, oi_chg=0, vol=0, iv=12, delta=delta, bid_qty=1000, ask_qty=1000)


def test_choose_underlying_uses_listed_expiries_not_weekdays():
    contracts = {
        "NSE_INDEX|Nifty 50": [{"expiry": "2026-10-27", "lot_size": 65}],
        "BSE_INDEX|SENSEX": [{"expiry": "2026-10-22", "lot_size": 20}],
    }
    pick = choose_underlying(dt.date(2026, 10, 21), ("NIFTY", "SENSEX"), 1, lambda key: contracts[key])
    assert pick["symbol"] == "SENSEX"
    assert pick["dte"] == 1
    assert pick["lot_size"] == 20
    assert choose_underlying(dt.date(2026, 10, 23), ("NIFTY", "SENSEX"), 1, lambda key: contracts[key]) is None


def test_to_bars_keeps_closed_session_bars_stamped_at_close():
    rows = [
        ["2026-10-19T15:35:00+05:30", 1, 1, 1, 1, 10, 0],
        ["2026-10-19T10:00:00+05:30", 3, 4, 2, 3, 30, 0],
        ["2026-10-19T09:55:00+05:30", 2, 3, 1, 2, 20, 0],
    ]
    now = dt.datetime(2026, 10, 19, 10, 3, tzinfo=IST)
    bars = to_bars(rows, 5, now)
    assert [bar.ts.time().isoformat() for bar in bars] == ["10:00:00"]
    hourly = to_bars([["2026-10-19T15:15:00+05:30", 1, 2, 1, 2, 5, 0]], 60, dt.datetime(2026, 10, 19, 15, 31, tzinfo=IST))
    assert hourly[0].ts.time() == dt.time(15, 30)


def test_wilder_rsi_bounds():
    assert rsi([float(x) for x in range(1, 40)]) == 100.0
    assert 0 <= rsi([100 + (-1) ** i * i for i in range(40)]) <= 100


def test_charges_include_stt_on_sells_and_brokerage():
    legs = [Leg(23000, "PE", -1, 20.0), Leg(22900, "PE", +1, 8.0)]
    fees = charges(legs, [10.0, 4.0], 65)
    assert 90 < fees < 130


def test_spread_hits_target_and_missing_quotes_force_exit():
    now = dt.datetime(2026, 10, 20, 10, 0, tzinfo=IST)
    engine = Engine(dict(CFG))
    engine.new_day("2026-10-20")
    from app.autotrader.engine import Pos

    def pos():
        return Pos(
            legs=[Leg(22900, "PE", -1, 20.0, 20.0), Leg(22800, "PE", +1, 6.0, 6.0)],
            side="CALL", mode="spread", symbol="NIFTY", expiry="2026-10-20", exchange="NSE", mult=65,
            ts_in=now.isoformat(), score=4, why="test", tp=0.6 * 14, sl=14, trigger_low=22950, trigger_high=23010,
        )

    engine.pos = pos()
    win = FakeFeed({(22900, "PE"): _quote(5.0, 5.2), (22800, "PE"): _quote(1.0, 1.1)}, now)
    row = engine.manage(win)
    assert row["reason"] == "TP"
    assert row["net"] > 0

    engine.pos = pos()
    empty = FakeFeed({}, now)
    assert engine.manage(empty) is None
    row = engine.manage(empty)
    assert row["reason"] == "NO_QUOTE"
    assert row["priced"] == "last_mark"


def test_signal_invalidation_closes_on_bar():
    now = dt.datetime(2026, 10, 20, 10, 5, tzinfo=IST)
    engine = Engine(dict(CFG))
    from app.autotrader.engine import Pos

    engine.pos = Pos(
        legs=[Leg(22900, "PE", -1, 20.0, 20.0), Leg(22800, "PE", +1, 6.0, 6.0)],
        side="CALL", mode="spread", symbol="NIFTY", expiry="2026-10-20", exchange="NSE", mult=65,
        ts_in=now.isoformat(), score=4, why="test", tp=8.4, sl=14, trigger_low=22950, trigger_high=23010,
    )
    bars = [Bar(now, 22960, 22965, 22930, 22940, 0)]
    chain = {(22900, "PE"): _quote(22.0, 22.4), (22800, "PE"): _quote(6.0, 6.2)}
    _decision, row = engine.on_bar(FakeFeed(chain, now, bars))
    assert row["reason"] == "INVALID"
