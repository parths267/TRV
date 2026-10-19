"""Live paper feed from the signed-in Upstox account. Read-only market data."""
from __future__ import annotations

import datetime as dt
import gzip
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from app.config import REPO_ROOT
from app.providers.upstox import UpstoxError, _request, fetch_chain, fetch_contracts, load_token

from .engine import Bar, Quote

IST = ZoneInfo("Asia/Kolkata")
DATA = REPO_ROOT / "data" / "autotrader"
SESSION_OPEN = dt.time(9, 15)
SESSION_CLOSE = dt.time(15, 30)

UNDERLYINGS = {
    "NIFTY": {"key": "NSE_INDEX|Nifty 50", "exchange": "NSE", "step": 50},
    "BANKNIFTY": {"key": "NSE_INDEX|Nifty Bank", "exchange": "NSE", "step": 100},
    "SENSEX": {"key": "BSE_INDEX|SENSEX", "exchange": "BSE", "step": 100},
}
VIX_KEY = "NSE_INDEX|India VIX"
_INTERVALS = {5: ("minutes", 5), 15: ("minutes", 15), 60: ("hours", 1)}
_INSTRUMENTS = "https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz"


def ist_now() -> dt.datetime:
    return dt.datetime.now(IST)


def _get(path: str) -> dict:
    token = load_token()
    if not token:
        raise UpstoxError(401, "Upstox login is required")
    return _request(f"https://api.upstox.com{path}", token=token)


def _candles(key: str, tf: int, start: dt.date, end: dt.date, intraday: bool) -> List[list]:
    unit, interval = _INTERVALS[tf]
    quoted = urllib.parse.quote(key, safe="")
    if intraday:
        path = f"/v3/historical-candle/intraday/{quoted}/{unit}/{interval}"
    else:
        path = f"/v3/historical-candle/{quoted}/{unit}/{interval}/{end.isoformat()}/{start.isoformat()}"
    body = _get(path)
    return (body.get("data") or {}).get("candles") or []


def to_bars(rows: List[list], tf: int, now: dt.datetime) -> List[Bar]:
    """Upstox stamps bars by open time. Keep session bars that have closed, stamped by close time."""
    bars: Dict[dt.datetime, Bar] = {}
    for row in rows:
        try:
            opened = dt.datetime.fromisoformat(str(row[0])).astimezone(IST)
        except ValueError:
            continue
        if not (SESSION_OPEN <= opened.time() < SESSION_CLOSE):
            continue
        session_end = opened.replace(hour=15, minute=30, second=0, microsecond=0)
        closed = min(opened + dt.timedelta(minutes=tf), session_end)
        if closed > now:
            continue
        bars[closed] = Bar(closed, float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5] or 0))
    return [bars[key] for key in sorted(bars)]


def nearest_expiry(expiries: List[str], today: dt.date) -> Optional[str]:
    upcoming = sorted(item for item in expiries if item >= today.isoformat())
    return upcoming[0] if upcoming else None


def choose_underlying(today: dt.date, underlyings, max_dte: int, contracts_for) -> Optional[dict]:
    """Trade the first index whose nearest option expiry is within max_dte calendar days."""
    for symbol in underlyings:
        spec = UNDERLYINGS.get(symbol)
        if spec is None:
            continue
        rows = contracts_for(spec["key"])
        expiries = sorted({str(row.get("expiry") or "")[:10] for row in rows if row.get("expiry")})
        expiry = nearest_expiry(expiries, today)
        if expiry is None:
            continue
        dte = (dt.date.fromisoformat(expiry) - today).days
        if dte <= max_dte:
            lot = next((int(row["lot_size"]) for row in rows if str(row.get("expiry", ""))[:10] == expiry and row.get("lot_size")), None)
            if lot:
                return {"symbol": symbol, "expiry": expiry, "dte": dte, "lot_size": lot, **spec}
    return None


def near_future(symbol: str, today: dt.date) -> Optional[dict]:
    """Near-month index future, from the Upstox instrument file cached once per day."""
    DATA.mkdir(parents=True, exist_ok=True)
    cache = DATA / f"futures_{today.isoformat()}.json"
    if cache.exists():
        rows = json.loads(cache.read_text(encoding="utf-8"))
    else:
        request = urllib.request.Request(_INSTRUMENTS, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=60) as response:
            everything = json.loads(gzip.decompress(response.read()))
        rows = [
            {
                "underlying": row.get("underlying_symbol"),
                "key": row.get("instrument_key"),
                "trading_symbol": row.get("trading_symbol"),
                "expiry": dt.datetime.fromtimestamp(int(row["expiry"]) / 1000, IST).date().isoformat(),
            }
            for row in everything
            if row.get("instrument_type") == "FUT" and row.get("underlying_symbol") in UNDERLYINGS and row.get("expiry")
        ]
        cache.write_text(json.dumps(rows), encoding="utf-8")
        for old in DATA.glob("futures_*.json"):
            if old != cache:
                old.unlink(missing_ok=True)
    live = sorted((row for row in rows if row["underlying"] == symbol and row["expiry"] >= today.isoformat()), key=lambda row: row["expiry"])
    return live[0] if live else None


class UpstoxFeed:
    """Same interface the engine expects: bars, futures bars, chain, VIX, and clock."""

    def __init__(self, pick: dict, today: dt.date, stop_file: Path):
        self.symbol = pick["symbol"]
        self.expiry = pick["expiry"]
        self.lot_size = pick["lot_size"]
        self.exchange = pick["exchange"]
        self.step = pick["step"]
        self.key = pick["key"]
        self.today = today
        self.stop_file = stop_file
        future = near_future(self.symbol, today)
        if future is None:
            raise UpstoxError(502, f"No near-month future listed for {self.symbol}")
        self.future = future
        self._now = ist_now()
        self._history: Dict[Tuple[str, int], List[list]] = {}
        self._bars: Dict[Tuple[str, int], List[Bar]] = {}
        self._chain: Dict[Tuple[int, str], Quote] = {}
        self._spot: Optional[float] = None
        self._vix: Optional[Tuple[float, Optional[float]]] = None
        self._chain_at = 0.0

    def _load_history(self, key: str, tf: int) -> List[list]:
        cached = self._history.get((key, tf))
        if cached is not None:
            return cached
        span = 40 if tf == 60 else 21
        rows = _candles(key, tf, self.today - dt.timedelta(days=span), self.today - dt.timedelta(days=1), intraday=False)
        self._history[(key, tf)] = rows
        return rows

    def refresh_bars(self) -> None:
        self._now = ist_now()
        for key, frames in ((self.key, (5, 15, 60)), (self.future["key"], (5,))):
            for tf in frames:
                rows = self._load_history(key, tf) + _candles(key, tf, self.today, self.today, intraday=True)
                self._bars[(key, tf)] = to_bars(rows, tf, self._now)
        vix_rows = _candles(VIX_KEY, 5, self.today, self.today, intraday=True)
        vix_bars = to_bars(vix_rows, 5, self._now)
        prev = _candles(VIX_KEY, 5, self.today - dt.timedelta(days=7), self.today - dt.timedelta(days=1), intraday=False)
        prev_bars = to_bars(prev, 5, self._now)
        self._vix = (vix_bars[-1].c, prev_bars[-1].c if prev_bars else None) if vix_bars else None

    def refresh_chain(self) -> None:
        self._now = ist_now()
        raw = fetch_chain(self.key, self.expiry)
        chain: Dict[Tuple[int, str], Quote] = {}
        spot = None
        for row in raw.get("rows") or []:
            strike = row.get("strike_price")
            if strike is None:
                continue
            spot = spot or row.get("underlying_spot_price")
            for typ, side in (("CE", "call_options"), ("PE", "put_options")):
                leg = row.get(side) or {}
                market = leg.get("market_data") or {}
                greeks = leg.get("option_greeks") or {}
                oi = float(market.get("oi") or 0)
                prev_oi = float(market.get("prev_oi") or 0)
                chain[(int(round(float(strike))), typ)] = Quote(
                    bid=float(market.get("bid_price") or 0),
                    ask=float(market.get("ask_price") or 0),
                    ltp=float(market.get("ltp") or 0),
                    oi=oi,
                    oi_chg=oi - prev_oi,
                    vol=float(market.get("volume") or 0),
                    iv=float(greeks.get("iv") or 0),
                    delta=float(greeks.get("delta") or 0),
                    bid_qty=float(market.get("bid_qty") or 0),
                    ask_qty=float(market.get("ask_qty") or 0),
                )
        self._chain = chain
        self._spot = float(spot) if spot else None
        self._chain_at = time.time()

    def now(self) -> dt.datetime:
        return self._now

    def spot(self) -> float:
        if self._spot is not None:
            return self._spot
        bars = self.bars(5)
        return bars[-1].c if bars else 0.0

    def bars(self, tf: int) -> List[Bar]:
        return self._bars.get((self.key, tf), [])

    def fut_bars(self, tf: int) -> List[Bar]:
        return self._bars.get((self.future["key"], tf), [])

    def chain(self) -> Dict[Tuple[int, str], Quote]:
        return self._chain

    def vix(self) -> Optional[Tuple[float, Optional[float]]]:
        return self._vix

    def data_age_seconds(self) -> Optional[int]:
        if not self._chain_at:
            return None
        bars = self.bars(5)
        chain_age = time.time() - self._chain_at
        if not bars:
            return None
        bar_age = (self._now - bars[-1].ts).total_seconds()
        return int(max(chain_age, bar_age - 300, 0))

    def stop_requested(self) -> bool:
        return self.stop_file.exists()


def contracts_for(key: str) -> List[dict]:
    return fetch_contracts(key)
