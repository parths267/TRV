"""Answers are assembled from tool results. The model, when configured, may only rephrase those results."""
from __future__ import annotations

import json
from typing import Any

import httpx

from app.config import get_settings
from app.market.analysis import ScanRules
from app.services.scans import nifty_symbols, run_highs, run_index_monitor, run_scanner

_SYSTEM = (
    "You explain Indian market tool output for a research product. "
    "Use only numbers that appear in the tool JSON. If a figure is absent, say it is unavailable. "
    "Separate facts, calculations, interpretation, and hypotheses. "
    "Do not predict returns or tell the user to buy or sell. "
    "Past backtests are not evidence of future profit."
)


def _section(kind: str, text: str) -> dict:
    return {"kind": kind, "text": text}


def answer_question(question: str) -> dict:
    text = question.strip()
    lower = text.lower()
    tools: list[dict[str, Any]] = []
    sections: list[dict] = []

    if any(word in lower for word in ("breakout", "scanner", "volume")):
        rules = ScanRules()
        payload = run_scanner(nifty_symbols(), rules, "1d")
        tools.append({"name": "scanner", "interval": "1d", "qualified": len(payload["qualified"]), "scanned": payload["scanned"]})
        names = ", ".join(row["symbol"] for row in payload["qualified"][:8]) or "none"
        sections.append(_section("fact", f"Daily scanner qualified {len(payload['qualified'])} of {payload['scanned']} snapshot names: {names}."))
        sections.append(_section("calculation", json.dumps(payload["rules"])))
        sections.append(_section("interpretation", payload["example_only"]))
    elif any(word in lower for word in ("52", "fifty", "high", "low")):
        payload = run_highs()
        tools.append({"name": "fifty_two_week", "method": payload["method"]})
        sections.append(_section("fact", f"Closing highs: {len(payload['new_closing_highs'])}. Approaching highs: {len(payload['approaching_highs'])}. Closing lows: {len(payload['new_closing_lows'])}."))
        sections.append(_section("calculation", payload["method"]))
        sections.append(_section("hypothesis", "Proximity to a prior high is not, by itself, a breakout or a reversal."))
    elif any(word in lower for word in ("bank", "index", "volatil", "breadth", "sector")):
        payload = run_index_monitor()
        tools.append({"name": "index_monitor", "example_triggered": payload["example_rule"]["triggered"]})
        move = next(row["move"] for row in payload["indices"] if row["id"] == "banknifty")
        if not move.get("available"):
            sections.append(_section("uncertainty", move.get("reason") or "Bank NIFTY window is unavailable."))
        else:
            sections.append(_section("fact", f"Bank NIFTY window change is {move['change_pct']}% from {move['from']} to {move['to']}."))
        sections.append(_section("fact", f"Example fast-drop rule triggered: {payload['example_rule']['triggered']}."))
        sections.append(_section("interpretation", "The rule describes the move. It does not identify a cause."))
        sections.append(_section("uncertainty", " ".join(payload["limitations"])))
    else:
        sections.append(_section("uncertainty", "No matching research tool was selected. Ask about breakouts, 52-week extremes, or index movement."))
        tools.append({"name": "none"})

    sections.append(_section("hypothesis", "Nothing in this reply is a recommendation to trade."))
    narrative = None
    settings = get_settings()
    if settings.openai_api_key and tools and tools[0]["name"] != "none":
        narrative = _rephrase(settings, text, {"sections": sections, "tools": tools})
    return {
        "question": text,
        "sections": sections,
        "tools": tools,
        "narrative": narrative,
        "model_used": bool(narrative),
        "disclaimer": "Tool output is research. It is not proof of a trading signal and not investment advice.",
    }


def _rephrase(settings, question: str, evidence: dict) -> str | None:
    url = (settings.openai_base_url or "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
    try:
        response = httpx.post(
            url,
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={
                "model": settings.openai_model,
                "temperature": 0.1,
                "messages": [
                    {"role": "system", "content": _SYSTEM},
                    {
                        "role": "user",
                        "content": json.dumps({"question": question, "evidence": evidence}),
                    },
                ],
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception as exc:
        return f"The language model was not used because the request failed: {exc}"
