"""Select the quote provider from DATA_MODE. Demo and live results are never mixed."""
from __future__ import annotations

from app.config import get_settings
from app.providers import demo, yahoo


def quotes():
    return demo if get_settings().demo_mode else yahoo


def provider_status() -> dict:
    settings = get_settings()
    quote_health = demo.health() if settings.demo_mode else yahoo.health()
    from app.providers.events import health as events_health

    screener = {"available": False, "reason": "tradingview-screener is not imported by the SaaS process."}
    try:
        import tradingview_screener  # noqa: F401

        screener = {
            "available": True,
            "reason": "Package is installed. SaaS scans still use Yahoo candles plus the engine indicators.",
        }
    except Exception as exc:
        screener = {"available": False, "reason": str(exc)}
    return {
        "data_mode": settings.data_mode,
        "live_trading_enabled": False,
        "quotes": quote_health,
        "events": events_health(),
        "analysis_engine": {
            "package": "tradingview-mcp",
            "reused": [
                "indicators_calc",
                "backtest_service.run_backtest",
                "backtest_service.compare_strategies",
                "backtest_service.walk_forward_backtest",
                "yahoo quote and daily/hourly history",
            ],
            "tradingview_screener": screener,
        },
    }
