"""Paper-only index-options engine, refined from paper_trader.py.

No order is sent to a broker. Fills are simulated at the live bid/ask plus slippage.
Decision gate: CALL / PUT / NO_TRADE from a 5-factor score plus a breakout confirmation.

Modes:
    "buy"    - single long CE/PE. Needs reward of at least twice the risk.
    "spread" - credit spread aligned with the signal. Wins often, loses more per loser.
Judge the system by expectancy and profit factor, not by win rate.
"""
from __future__ import annotations

import datetime as dt
import statistics as st
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple

T = dt.time

CFG: dict = dict(
    mode="spread",
    lots=1,
    underlyings=("NIFTY", "SENSEX"),
    max_dte=1,
    step={"NIFTY": 50, "SENSEX": 100, "BANKNIFTY": 100},
    width={"NIFTY": 100, "SENSEX": 300, "BANKNIFTY": 300},
    entry_from=T(9, 45), entry_until=T(13, 30), squareoff=T(15, 15),
    min_score=4,
    max_trades=2, max_consec_losses=2,
    daily_loss_cap=3000.0,
    max_risk_per_trade=4000.0,
    slip=0.003,
    max_spread_pct=0.03, min_oi=50000,
    hour_band_pct=0.05,
    vix_max=20.0, vix_jump_pct=8.0,
    stale_seconds=180,
    missing_quote_exits=2,
    min_tp_to_cost=2.0,
    buy_delta=0.50, buy_sl=0.30, buy_tp=0.60, buy_time_stop_bars=12,
    spr_short_delta=0.20, spr_tp=0.60, spr_sl_mult=2.0, spr_min_credit_pct=0.12,
)

EXCHANGE_TXN = {"NSE": 0.0003503, "BSE": 0.000325}


@dataclass
class Bar:
    ts: dt.datetime
    o: float
    h: float
    l: float
    c: float
    v: float


@dataclass
class Quote:
    bid: float
    ask: float
    ltp: float
    oi: float
    oi_chg: float
    vol: float
    iv: float
    delta: float
    bid_qty: float = 0.0
    ask_qty: float = 0.0


@dataclass
class Leg:
    strike: int
    typ: str
    qty: int
    entry: float
    mark: float = 0.0


@dataclass
class Pos:
    legs: List[Leg]
    side: str
    mode: str
    symbol: str
    expiry: str
    exchange: str
    mult: int
    ts_in: str
    score: int
    why: str
    tp: float
    sl: float
    trigger_low: float
    trigger_high: float
    bars_held: int = 0
    missing: int = 0


@dataclass
class Decision:
    side: str
    score: int
    why: str
    factors: Dict[str, int] = field(default_factory=dict)


def ema(xs: List[float], n: int) -> float:
    seed = st.mean(xs[:n]) if len(xs) >= n else xs[0]
    k, e = 2 / (n + 1), seed
    for x in xs[n:] if len(xs) >= n else xs[1:]:
        e = x * k + e * (1 - k)
    return e


def rsi(xs: List[float], n: int = 14) -> float:
    deltas = [b - a for a, b in zip(xs[:-1], xs[1:])]
    if len(deltas) < n:
        return 50.0
    gain = sum(max(x, 0) for x in deltas[:n]) / n
    loss = sum(max(-x, 0) for x in deltas[:n]) / n
    for x in deltas[n:]:
        gain = (gain * (n - 1) + max(x, 0)) / n
        loss = (loss * (n - 1) + max(-x, 0)) / n
    return 100.0 if loss == 0 else 100 - 100 / (1 + gain / loss)


def atr(bars: List[Bar], n: int = 14) -> float:
    trs = [max(b.h - b.l, abs(b.h - p.c), abs(b.l - p.c)) for p, b in zip(bars[-n - 1:-1], bars[-n:])]
    return sum(trs) / len(trs) if trs else 0.0


def vwap(bars: List[Bar]) -> Optional[float]:
    volume = sum(b.v for b in bars)
    if volume <= 0:
        return None
    return sum((b.h + b.l + b.c) / 3 * b.v for b in bars) / volume


def chain_bias(chain: Dict[Tuple[int, str], Quote], spot: float, step: int) -> Tuple[int, str]:
    atm = round(spot / step) * step
    pe = ce = 0.0
    for (strike, typ), quote in chain.items():
        if abs(strike - atm) <= 5 * step:
            if typ == "PE":
                pe += max(quote.oi_chg, 0)
            else:
                ce += max(quote.oi_chg, 0)
    ratio = (pe + 1) / (ce + 1)
    return (1 if ratio > 1.2 else -1 if ratio < 0.83 else 0), f"PE/CE OI-add {ratio:.2f}"


def evaluate(feed, cfg: dict = CFG) -> Decision:
    """CALL, PUT, or NO_TRADE. A trade is never forced."""
    b5, b15, b60 = feed.bars(5), feed.bars(15), feed.bars(60)
    if len(b15) < 150 or len(b60) < 60 or len(b5) < 20:
        return Decision("NO_TRADE", 0, f"warm-up: 5m {len(b5)}, 15m {len(b15)}, 1h {len(b60)}")
    spot, step = feed.spot(), feed.step
    why: List[str] = []
    factors: Dict[str, int] = {}

    c15 = [b.c for b in b15]
    e20, e50 = ema(c15, 20), ema(c15, 50)
    f1 = 1 if (e20 > e50 and c15[-1] > e20) else -1 if (e20 < e50 and c15[-1] < e20) else 0
    factors["trend_15m"] = f1
    why.append(f"15m trend {f1:+d}")

    c60 = [b.c for b in b60]
    e21 = ema(c60, 21)
    band = e21 * cfg["hour_band_pct"] / 100
    f2 = 1 if c60[-1] > e21 + band else -1 if c60[-1] < e21 - band else 0
    factors["hour_ema21"] = f2
    why.append(f"1H vs EMA21 {f2:+d}")

    fut = feed.fut_bars(5)
    session = [b for b in fut if b.ts.date() == feed.now().date()]
    level = vwap(session)
    if level is None or not session:
        return Decision("NO_TRADE", 0, "futures VWAP unavailable", factors)
    f3 = 1 if session[-1].c > level else -1
    factors["fut_vwap"] = f3
    why.append(f"5m fut vs VWAP {f3:+d}")

    r = rsi(c15)
    f4 = 1 if 55 <= r <= 72 else -1 if 28 <= r <= 45 else 0
    factors["rsi_15m"] = f4
    why.append(f"RSI15 {r:.0f} {f4:+d}")

    f5, text = chain_bias(feed.chain(), spot, step)
    factors["oi_bias"] = f5
    why.append(f"{text} {f5:+d}")

    score = f1 + f2 + f3 + f4 + f5
    reasons = "; ".join(why)
    if atr(b5) < 0.0004 * spot:
        return Decision("NO_TRADE", score, "range too tight; " + reasons, factors)

    vix = feed.vix()
    if vix is not None:
        last, prev = vix
        if last > cfg["vix_max"]:
            return Decision("NO_TRADE", score, f"India VIX {last:.2f} above {cfg['vix_max']}; " + reasons, factors)
        if prev and (last - prev) / prev * 100 >= cfg["vix_jump_pct"]:
            return Decision("NO_TRADE", score, f"India VIX up {(last - prev) / prev * 100:.1f}% today; " + reasons, factors)

    prev3 = b5[-4:-1]
    if score >= cfg["min_score"] and b5[-1].c > max(b.h for b in prev3):
        return Decision("CALL", score, reasons, factors)
    if score <= -cfg["min_score"] and b5[-1].c < min(b.l for b in prev3):
        return Decision("PUT", score, reasons, factors)
    return Decision("NO_TRADE", score, "no confirmation; " + reasons, factors)


def charges(legs: List[Leg], exits: List[float], mult: int, exchange: str = "NSE") -> float:
    """Approximate Indian index-option costs for a round trip on every leg.

    Rs 20 per order, STT 0.1% of sell premium, exchange transaction charge,
    SEBI Rs 10 per crore, stamp 0.003% of buy premium, GST 18% on brokerage,
    exchange, and SEBI charges.
    """
    brokerage = 20.0 * 2 * len(legs)
    sell = buy = 0.0
    for leg, exit_px in zip(legs, exits):
        if leg.qty < 0:
            sell += leg.entry * mult
            buy += exit_px * mult
        else:
            buy += leg.entry * mult
            sell += exit_px * mult
    turnover = sell + buy
    txn = EXCHANGE_TXN.get(exchange, EXCHANGE_TXN["NSE"]) * turnover
    sebi = 0.000001 * turnover
    stamp = 0.00003 * buy
    stt = 0.001 * sell
    gst = 0.18 * (brokerage + txn + sebi)
    return brokerage + stt + txn + sebi + stamp + gst


class Engine:
    def __init__(self, cfg: dict = CFG):
        self.cfg = cfg
        self.pos: Optional[Pos] = None
        self.day = ""
        self.n_trades = 0
        self.consec = 0
        self.day_pnl = 0.0
        self.closed: List[dict] = []

    def new_day(self, day: str) -> None:
        self.day = day
        self.n_trades = 0
        self.consec = 0
        self.day_pnl = 0.0

    def _liquid(self, quote: Optional[Quote], qty: int) -> bool:
        if quote is None or quote.ask <= 0 or quote.bid <= 0:
            return False
        mid = (quote.ask + quote.bid) / 2
        spread_ok = (quote.ask - quote.bid) <= max(0.10, self.cfg["max_spread_pct"] * mid) + 1e-9
        depth_ok = quote.bid_qty >= qty and quote.ask_qty >= qty if (quote.bid_qty or quote.ask_qty) else True
        return spread_ok and depth_ok and quote.oi >= self.cfg["min_oi"]

    def _exit_px(self, leg: Leg, chain) -> Optional[float]:
        quote = chain.get((leg.strike, leg.typ))
        if quote is None:
            return None
        slip = self.cfg["slip"]
        if leg.qty > 0:
            return quote.bid * (1 - slip) if quote.bid > 0 else (quote.ltp * (1 - slip) if quote.ltp > 0 else None)
        return quote.ask * (1 + slip) if quote.ask > 0 else (quote.ltp * (1 + slip) if quote.ltp > 0 else None)

    def _pnl_unit(self, pos: Pos, chain) -> Optional[float]:
        total = 0.0
        for leg in pos.legs:
            px = self._exit_px(leg, chain)
            if px is None:
                return None
            leg.mark = px
            total += leg.qty * (px - leg.entry)
        return total

    def manage(self, feed) -> Optional[dict]:
        """Run every minute. Stops and targets use the live chain, not bar closes."""
        if not self.pos:
            return None
        now = feed.now()
        chain = feed.chain()
        unit = self._pnl_unit(self.pos, chain)
        reason = None
        if feed.stop_requested():
            reason = "STOP"
        elif now.time() >= self.cfg["squareoff"]:
            reason = "EOD"
        elif unit is None:
            self.pos.missing += 1
            if self.pos.missing >= self.cfg["missing_quote_exits"]:
                reason = "NO_QUOTE"
        else:
            self.pos.missing = 0
            if unit >= self.pos.tp:
                reason = "TP"
            elif unit <= -self.pos.sl:
                reason = "SL"
        if reason:
            return self.close(feed, reason)
        return None

    def on_bar(self, feed) -> Tuple[Optional[Decision], Optional[dict]]:
        """Run once per closed 5-minute bar."""
        if self.pos:
            self.pos.bars_held += 1
            last = feed.bars(5)[-1]
            invalid = (self.pos.side == "CALL" and last.c < self.pos.trigger_low) or (
                self.pos.side == "PUT" and last.c > self.pos.trigger_high
            )
            if invalid:
                return None, self.close(feed, "INVALID")
            if self.pos.mode == "buy" and self.pos.bars_held >= self.cfg["buy_time_stop_bars"]:
                return None, self.close(feed, "TIME")
            return None, None
        cfg = self.cfg
        now = feed.now().time()
        if feed.stop_requested():
            return Decision("NO_TRADE", 0, "stop file present"), None
        if not (cfg["entry_from"] <= now <= cfg["entry_until"]):
            return Decision("NO_TRADE", 0, "outside the entry window"), None
        if self.n_trades >= cfg["max_trades"]:
            return Decision("NO_TRADE", 0, "daily trade limit reached"), None
        if self.consec >= cfg["max_consec_losses"]:
            return Decision("NO_TRADE", 0, "consecutive-loss limit reached"), None
        if self.day_pnl <= -cfg["daily_loss_cap"]:
            return Decision("NO_TRADE", 0, "daily loss cap reached"), None
        age = feed.data_age_seconds()
        if age is None or age > cfg["stale_seconds"]:
            return Decision("NO_TRADE", 0, f"data is stale ({age} s)"), None
        decision = evaluate(feed, cfg)
        if decision.side != "NO_TRADE":
            skipped = self.open(feed, decision)
            if skipped:
                decision = Decision("NO_TRADE", decision.score, f"{decision.side} signal skipped: {skipped}; {decision.why}", decision.factors)
        return decision, None

    def open(self, feed, decision: Decision) -> Optional[str]:
        cfg, spot, step, sym = self.cfg, feed.spot(), feed.step, feed.symbol
        chain = feed.chain()
        mult = cfg["lots"] * feed.lot_size
        atm = round(spot / step) * step
        slip = cfg["slip"]
        side = decision.side
        typ = "CE" if side == "CALL" else "PE"
        if cfg["mode"] == "buy":
            candidates = [
                (abs(abs(chain[k].delta) - cfg["buy_delta"]), k[0]) for k in chain
                if k[1] == typ and abs(k[0] - atm) <= 3 * step and self._liquid(chain[k], mult)
            ]
            if not candidates:
                return "no liquid strike near the money"
            strike = min(candidates)[1]
            entry = chain[(strike, typ)].ask * (1 + slip)
            legs = [Leg(strike, typ, +1, entry, entry)]
            tp, sl = entry * cfg["buy_tp"], entry * cfg["buy_sl"]
        else:
            short_typ = "PE" if side == "CALL" else "CE"
            width = cfg["width"][sym]
            sign = -1 if short_typ == "PE" else 1
            candidates = [
                (abs(abs(chain[k].delta) - cfg["spr_short_delta"]), k[0]) for k in chain
                if k[1] == short_typ and (k[0] - atm) * sign > 0 and self._liquid(chain[k], mult)
            ]
            if not candidates:
                return "no liquid short strike"
            short_k = min(candidates)[1]
            long_k = short_k + sign * width
            if not self._liquid(chain.get((long_k, short_typ)), mult):
                return f"hedge strike {long_k} is not liquid"
            short_px = chain[(short_k, short_typ)].bid * (1 - slip)
            long_px = chain[(long_k, short_typ)].ask * (1 + slip)
            credit = short_px - long_px
            if credit < cfg["spr_min_credit_pct"] * width:
                return f"credit {credit:.2f} below {cfg['spr_min_credit_pct'] * width:.2f}"
            legs = [Leg(short_k, short_typ, -1, short_px, short_px), Leg(long_k, short_typ, +1, long_px, long_px)]
            tp = cfg["spr_tp"] * credit
            sl = min((cfg["spr_sl_mult"] - 1) * credit, 0.9 * (width - credit))
        if sl * mult > cfg["max_risk_per_trade"]:
            return f"risk Rs {sl * mult:.0f} above the Rs {cfg['max_risk_per_trade']:.0f} cap"
        fees = charges(legs, [leg.entry for leg in legs], mult, feed.exchange)
        if tp * mult < cfg["min_tp_to_cost"] * fees:
            return f"target Rs {tp * mult:.0f} is under {cfg['min_tp_to_cost']}x costs Rs {fees:.0f}"
        trigger = feed.bars(5)[-4:-1]
        self.pos = Pos(
            legs=legs, side=side, mode=cfg["mode"], symbol=sym, expiry=feed.expiry,
            exchange=feed.exchange, mult=mult, ts_in=feed.now().isoformat(),
            score=decision.score, why=decision.why, tp=tp, sl=sl,
            trigger_low=min(b.l for b in trigger), trigger_high=max(b.h for b in trigger),
        )
        self.n_trades += 1
        return None

    def close(self, feed, reason: str) -> dict:
        pos, chain = self.pos, feed.chain()
        exits = []
        for leg in pos.legs:
            px = self._exit_px(leg, chain)
            exits.append(px if px is not None else (leg.mark or leg.entry))
        gross = sum(leg.qty * (x - leg.entry) for leg, x in zip(pos.legs, exits)) * pos.mult
        fees = charges(pos.legs, exits, pos.mult, pos.exchange)
        net = gross - fees
        self.day_pnl += net
        self.consec = self.consec + 1 if net <= 0 else 0
        row = dict(
            date=pos.ts_in[:10], instrument=pos.symbol, expiry=pos.expiry, mode=pos.mode, side=pos.side,
            t_in=pos.ts_in[11:19], t_out=feed.now().time().isoformat(timespec="seconds"), reason=reason,
            legs=" | ".join(f"{'+' if l.qty > 0 else '-'}{l.strike}{l.typ}@{l.entry:.2f}->{x:.2f}" for l, x in zip(pos.legs, exits)),
            gross=round(gross, 2), fees=round(fees, 2), net=round(net, 2),
            score=pos.score, why=pos.why,
            priced="last_mark" if reason == "NO_QUOTE" else "bid_ask",
        )
        self.closed.append(row)
        self.pos = None
        return row

    def to_state(self) -> dict:
        return {
            "day": self.day,
            "n_trades": self.n_trades,
            "consec": self.consec,
            "day_pnl": round(self.day_pnl, 2),
            "pos": None if self.pos is None else asdict(self.pos),
        }

    def load_state(self, state: dict) -> None:
        self.day = state.get("day", "")
        self.n_trades = int(state.get("n_trades", 0))
        self.consec = int(state.get("consec", 0))
        self.day_pnl = float(state.get("day_pnl", 0.0))
        raw = state.get("pos")
        if raw:
            legs = [Leg(**leg) for leg in raw.pop("legs")]
            self.pos = Pos(legs=legs, **raw)


def summary(rows: List[dict]) -> dict:
    nets = [float(r["net"]) for r in rows]
    if not nets:
        return {"trades": 0}
    wins = [x for x in nets if x > 0]
    losses = [-x for x in nets if x <= 0]
    avg_win = st.mean(wins) if wins else 0.0
    avg_loss = st.mean(losses) if losses else 0.0
    return {
        "trades": len(nets),
        "win_pct": round(len(wins) / len(nets) * 100, 1),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "breakeven_win_pct": round(avg_loss / (avg_win + avg_loss) * 100, 1) if (avg_win + avg_loss) else None,
        "expectancy": round(sum(nets) / len(nets), 2),
        "profit_factor": round(sum(wins) / sum(losses), 2) if losses and sum(losses) else None,
        "net_pnl": round(sum(nets), 2),
    }
