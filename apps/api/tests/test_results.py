from datetime import date

from app.market.universe import top_250_symbols
from app.providers.events import map_result_rows


def test_upcoming_results_keep_financial_results_only():
    rows = map_result_rows(
        [
            {
                "symbol": "TCS",
                "company": "Tata Consultancy Services Limited",
                "purpose": "Financial Results",
                "bm_desc": "To consider the financial results for the period ended September 30, 2026",
                "date": "27-Oct-2026",
            },
            {
                "symbol": "INFY",
                "company": "Infosys Limited",
                "purpose": "Financial Results/Dividend",
                "bm_desc": "Results and dividend",
                "date": "19-Oct-2026",
            },
            {
                "symbol": "OLD",
                "company": "Old Limited",
                "purpose": "Financial Results",
                "bm_desc": "Already held",
                "date": "01-Oct-2026",
            },
            {
                "symbol": "BUY",
                "company": "Buyback Limited",
                "purpose": "Buyback",
                "bm_desc": "Buyback",
                "date": "27-Oct-2026",
            },
            {
                "symbol": "TCS",
                "company": "Tata Consultancy Services Limited",
                "purpose": "Financial Results",
                "bm_desc": "duplicate",
                "date": "27-Oct-2026",
            },
        ],
        date(2026, 10, 19),
    )
    assert [row["symbol"] for row in rows] == ["INFY", "TCS"]
    assert rows[1]["date"] == "2026-10-27"
    assert rows[1]["detail"].startswith("To consider")
    assert rows[0]["source_url"].endswith("event-calendar")


def test_top_250_is_nifty_100_plus_midcap_150():
    symbols = top_250_symbols()
    assert len(symbols) == 250
    assert "BAJFINANCE" in symbols
    assert "RELIANCE" in symbols
