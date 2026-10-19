import datetime as dt

from app.autotrader import notify
from app.providers.upstox import IST
from app.autotrader.engine import CFG, Engine, Leg, Pos


def _pos():
    legs = [Leg(22800, "PE", -1, 42.0, 42.0), Leg(22700, "PE", 1, 18.0, 18.0)]
    return Pos(
        legs=legs, side="CALL", mode="spread", symbol="NIFTY", expiry="2026-10-20", exchange="NSE",
        mult=65, ts_in="2026-10-20T10:05:00+05:30", score=4, why="trend up", tp=14.4, sl=24.0,
        trigger_low=22850.0, trigger_high=22900.0,
    )


def test_entry_message_lists_legs_and_risk():
    text = notify.opened_text(_pos())
    assert "PAPER ENTRY · NIFTY 2026-10-20" in text
    assert "SELL 22800 PE @ 42.00" in text and "BUY 22700 PE @ 18.00" in text
    assert "Credit 24.00 x 65 = ₹1,560" in text
    assert "Target ₹936 · stop ₹1,560" in text


def test_exit_message():
    engine = Engine(CFG)
    engine.new_day("2026-10-20")
    engine.n_trades, engine.day_pnl = 2, -3100.0
    row = {"instrument": "NIFTY", "side": "CALL", "mode": "spread", "reason": "SL", "t_in": "10:05:00",
           "t_out": "11:20:00", "legs": "-22800PE@42.00->70.00", "net": "-1650.5", "fees": "88.2"}
    text = notify.closed_text(row, engine)
    assert "stop loss at 11:20:00" in text and "Net -₹1,650" in text and "-₹3,100" in text


def test_morning_results_only_when_there_are_results(monkeypatch):
    from app.autotrader import runner

    sent = []
    monkeypatch.setattr(notify, "send_once", lambda day, key, text: sent.append((key, text)))
    rows = {"2026-10-20": [], "2026-10-21": [{"symbol": "SRF", "company": "SRF Limited", "date": "2026-10-21"}]}
    monkeypatch.setattr(notify, "results_for", lambda day: rows[day.isoformat()])
    checked: set = set()
    runner._morning_results(dt.datetime(2026, 10, 20, 7, 59, tzinfo=IST), checked)
    runner._morning_results(dt.datetime(2026, 10, 20, 8, 0, tzinfo=IST), checked)
    assert sent == [] and "2026-10-20" in checked
    runner._morning_results(dt.datetime(2026, 10, 21, 8, 1, tzinfo=IST), checked)
    runner._morning_results(dt.datetime(2026, 10, 21, 8, 3, tzinfo=IST), checked)
    assert len(sent) == 1 and "1. SRF Limited (SRF)" in sent[0][1]


def test_morning_results_retry_when_calendar_is_down(monkeypatch):
    from app.autotrader import runner

    monkeypatch.setattr(notify, "results_for", lambda day: None)
    checked: set = set()
    runner._morning_results(dt.datetime(2026, 10, 21, 8, 0, tzinfo=IST), checked)
    assert checked == set()


def test_send_once_per_day(monkeypatch, tmp_path):
    sent = []
    monkeypatch.setattr(notify, "SENT", tmp_path / "notified.json")
    monkeypatch.setattr(notify, "send", sent.append)
    monkeypatch.setattr(notify, "configured", lambda: True)
    notify.send_once("2026-10-20", "summary", "a")
    notify.send_once("2026-10-20", "summary", "b")
    notify.send_once("2026-10-21", "summary", "c")
    assert sent == ["a", "c"]
