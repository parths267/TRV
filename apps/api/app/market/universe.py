"""Configurable Indian index and equity universe.

NIFTY 50 names are a published snapshot, not a live membership feed from NSE Indices.
Replace this table when the index is reconstituted. Yahoo symbols follow the
``.NS`` convention; ``M&M`` is encoded by the chart client.
"""
from __future__ import annotations

from dataclasses import dataclass

SNAPSHOT_NOTE = (
    "NIFTY 50 snapshot dated 2026-06-11 from a published NSE Indices constituent file. "
    "This is not a live membership feed and can lag reconstitutions."
)


@dataclass(frozen=True)
class Instrument:
    symbol: str
    name: str
    exchange: str
    sector: str
    yahoo: str

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "exchange": self.exchange,
            "sector": self.sector,
            "yahoo": self.yahoo,
        }


def _ns(symbol: str, name: str, sector: str) -> Instrument:
    yahoo = f"{symbol}.NS"
    return Instrument(symbol, name, "NSE", sector, yahoo)


NIFTY_50: tuple[Instrument, ...] = (
    _ns("ADANIENT", "Adani Enterprises", "Services"),
    _ns("ADANIPORTS", "Adani Ports", "Services"),
    _ns("APOLLOHOSP", "Apollo Hospitals", "Healthcare"),
    _ns("ASIANPAINT", "Asian Paints", "Materials"),
    _ns("AXISBANK", "Axis Bank", "Financials"),
    _ns("BAJAJ-AUTO", "Bajaj Auto", "Auto"),
    _ns("BAJAJFINSV", "Bajaj Finserv", "Financials"),
    _ns("BAJFINANCE", "Bajaj Finance", "Financials"),
    _ns("BEL", "Bharat Electronics", "Industrials"),
    _ns("BHARTIARTL", "Bharti Airtel", "Telecom"),
    _ns("CIPLA", "Cipla", "Healthcare"),
    _ns("COALINDIA", "Coal India", "Energy"),
    _ns("DRREDDY", "Dr Reddy's Laboratories", "Healthcare"),
    _ns("EICHERMOT", "Eicher Motors", "Auto"),
    _ns("ETERNAL", "Eternal", "Services"),
    _ns("GRASIM", "Grasim Industries", "Materials"),
    _ns("HCLTECH", "HCL Technologies", "Information Technology"),
    _ns("HDFCBANK", "HDFC Bank", "Financials"),
    _ns("HDFCLIFE", "HDFC Life Insurance", "Financials"),
    _ns("HINDALCO", "Hindalco Industries", "Materials"),
    _ns("HINDUNILVR", "Hindustan Unilever", "Consumer"),
    _ns("ICICIBANK", "ICICI Bank", "Financials"),
    _ns("INDIGO", "InterGlobe Aviation", "Services"),
    _ns("INFY", "Infosys", "Information Technology"),
    _ns("ITC", "ITC", "Consumer"),
    _ns("JIOFIN", "Jio Financial Services", "Financials"),
    _ns("JSWSTEEL", "JSW Steel", "Materials"),
    _ns("KOTAKBANK", "Kotak Mahindra Bank", "Financials"),
    _ns("LT", "Larsen & Toubro", "Industrials"),
    _ns("M&M", "Mahindra & Mahindra", "Auto"),
    _ns("MARUTI", "Maruti Suzuki", "Auto"),
    _ns("MAXHEALTH", "Max Healthcare", "Healthcare"),
    _ns("NESTLEIND", "Nestle India", "Consumer"),
    _ns("NTPC", "NTPC", "Energy"),
    _ns("ONGC", "ONGC", "Energy"),
    _ns("POWERGRID", "Power Grid Corporation", "Energy"),
    _ns("RELIANCE", "Reliance Industries", "Energy"),
    _ns("SBILIFE", "SBI Life Insurance", "Financials"),
    _ns("SBIN", "State Bank of India", "Financials"),
    _ns("SHRIRAMFIN", "Shriram Finance", "Financials"),
    _ns("SUNPHARMA", "Sun Pharmaceutical", "Healthcare"),
    _ns("TATACONSUM", "Tata Consumer Products", "Consumer"),
    _ns("TATASTEEL", "Tata Steel", "Materials"),
    _ns("TCS", "Tata Consultancy Services", "Information Technology"),
    _ns("TECHM", "Tech Mahindra", "Information Technology"),
    _ns("TITAN", "Titan Company", "Consumer"),
    _ns("TMPV", "Tata Motors Passenger Vehicles", "Auto"),
    _ns("TRENT", "Trent", "Consumer"),
    _ns("ULTRACEMCO", "UltraTech Cement", "Materials"),
    _ns("WIPRO", "Wipro", "Information Technology"),
)

# Large banking names used only as supporting evidence for index alerts.
# This is not the official NIFTY Bank membership file.
BANKING_WATCH: tuple[str, ...] = (
    "HDFCBANK",
    "ICICIBANK",
    "SBIN",
    "KOTAKBANK",
    "AXISBANK",
)

INDICES: tuple[dict, ...] = (
    {"id": "nifty50", "name": "NIFTY 50", "yahoo": "^NSEI", "tradingview": "NSE:NIFTY"},
    {"id": "banknifty", "name": "NIFTY Bank", "yahoo": "^NSEBANK", "tradingview": "NSE:BANKNIFTY"},
    {"id": "sensex", "name": "BSE Sensex", "yahoo": "^BSESN", "tradingview": "BSE:SENSEX"},
    {
        "id": "niftyfin",
        "name": "NIFTY Financial Services",
        "yahoo": "^CNXFIN",
        "tradingview": "NSE:CNXFINANCE",
    },
    {"id": "niftyit", "name": "NIFTY IT", "yahoo": "^CNXIT", "tradingview": "NSE:CNXIT"},
    {
        "id": "niftymid",
        "name": "NIFTY Midcap 100",
        "yahoo": "NIFTY_MIDCAP_100.NS",
        "tradingview": "NSE:NIFTYMIDCAP100",
    },
    {
        "id": "niftysmall",
        "name": "NIFTY Smallcap 100",
        "yahoo": "^CNXSC",
        "tradingview": "NSE:NIFTYSMLCAP100",
    },
)

BY_SYMBOL = {item.symbol: item for item in NIFTY_50}

BROAD_SNAPSHOT_NOTE = (
    "NIFTY 500 snapshot dated 2026-10-11 from the NSE Indices constituent file. "
    "It covers the large, mid, and small-cap names used by the Nifty, sector, and size indices, "
    "including the names that also sit in the Sensex and Nifty Bank. "
    "This is not a live membership feed and can lag reconstitutions."
)


TOP_250_NOTE = (
    "Nifty 100 and Nifty Midcap 150 constituent files saved on 19 Oct 2026. "
    "Together they are the exchange's top 250 companies. Membership can lag the next reconstitution."
)


def top_250_symbols() -> set[str]:
    """Nifty 100 plus Nifty Midcap 150. That is the exchange's top 250 names."""
    import csv
    from pathlib import Path

    folder = Path(__file__).resolve().parent / "data"
    symbols: set[str] = set()
    for name in ("nifty100_2026-10-19.csv", "niftymidcap150_2026-10-19.csv"):
        path = folder / name
        if not path.exists():
            continue
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for record in csv.DictReader(handle):
                symbol = (record.get("Symbol") or "").strip().upper()
                if symbol:
                    symbols.add(symbol)
    return symbols


def broad_universe() -> tuple[Instrument, ...]:
    """Index constituents beyond the NIFTY 50 list. Loaded from the stored snapshot."""
    import csv
    from pathlib import Path

    path = Path(__file__).resolve().parent / "data" / "nifty500_2026-10-11.csv"
    if not path.exists():
        return NIFTY_50
    rows: list[Instrument] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for record in csv.DictReader(handle):
            symbol = (record.get("Symbol") or "").strip().upper()
            name = (record.get("Company Name") or "").strip()
            sector = (record.get("Industry") or "").strip() or "Unclassified"
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            rows.append(Instrument(symbol, name or symbol, "NSE", sector, f"{symbol}.NS"))
    return tuple(rows) if rows else NIFTY_50


def yahoo_for(symbol: str, exchange: str = "NSE") -> str:
    known = BY_SYMBOL.get(symbol.upper())
    if known:
        return known.yahoo
    suffix = ".BO" if exchange.upper() == "BSE" else ".NS"
    return f"{symbol.upper()}{suffix}"
