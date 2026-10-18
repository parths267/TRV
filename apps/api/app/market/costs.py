"""Approximate NSE equity delivery costs.

These are assumptions for research, not a tax calculation and not a broker quote.
The analysis engine applies one symmetric percent on entry and one on exit, so
one-sided charges (STT on sell, stamp on buy) are spread across both sides.
The round trip matches; the per-side split is an allocation, not the statute.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EquityCostModel:
    brokerage_pct: float = 0.03
    stt_sell_pct: float = 0.1
    exchange_pct: float = 0.00297
    sebi_pct: float = 0.0001
    stamp_buy_pct: float = 0.015
    gst_rate: float = 0.18
    slippage_pct: float = 0.05

    def breakdown(self) -> dict:
        brokerage_round = self.brokerage_pct * 2
        exchange_round = self.exchange_pct * 2
        sebi_round = self.sebi_pct * 2
        gst = self.gst_rate * (brokerage_round + exchange_round + sebi_round)
        round_trip = brokerage_round + self.stt_sell_pct + exchange_round + sebi_round + self.stamp_buy_pct + gst
        per_side = round_trip / 2
        return {
            "market": "NSE equity delivery (approximation)",
            "brokerage_round_trip_pct": round(brokerage_round, 6),
            "stt_sell_pct": self.stt_sell_pct,
            "exchange_round_trip_pct": round(exchange_round, 6),
            "sebi_round_trip_pct": round(sebi_round, 6),
            "stamp_buy_pct": self.stamp_buy_pct,
            "gst_pct": round(gst, 6),
            "round_trip_pct": round(round_trip, 6),
            "engine_commission_pct_per_side": round(per_side, 6),
            "slippage_pct_per_side": self.slippage_pct,
            "not_tax_advice": True,
            "engine_note": (
                "tradingview-mcp applies (commission_pct + slippage_pct) on the way in "
                "and again on the way out. commission_pct is half of the statutory-style "
                "round trip so the combined deduction matches that round trip."
            ),
        }

    def fees_inr(self, side: str, traded_value: float) -> float:
        """Cash fee for one paper fill. Slippage is applied to the price, not here."""
        brokerage = traded_value * self.brokerage_pct / 100
        exchange = traded_value * self.exchange_pct / 100
        sebi = traded_value * self.sebi_pct / 100
        stt = traded_value * self.stt_sell_pct / 100 if side == "sell" else 0.0
        stamp = traded_value * self.stamp_buy_pct / 100 if side == "buy" else 0.0
        gst = self.gst_rate * (brokerage + exchange + sebi)
        return round(brokerage + exchange + sebi + stt + stamp + gst, 2)


DEFAULT_COSTS = EquityCostModel()
