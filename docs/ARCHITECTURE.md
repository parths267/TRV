# Architecture

The product is an Indian-market research SaaS wrapped around the existing MIT-licensed `tradingview-mcp` engine. The engine is still a Python MCP server. It was not replaced.

## What the engine already does

- 37 MCP tools for quotes, screeners, multi-timeframe technicals, news, and backtests.
- NSE and BSE are accepted exchanges. `NSE:NIFTY`, `NSE:BANKNIFTY`, and `BSE:SENSEX` resolve from common aliases, and the packaged coin lists contain NSE and BSE symbols.
- Pure-Python indicators in `src/tradingview_mcp/core/services/indicators_calc.py`: EMA, SMA, RSI, Bollinger, MACD, ATR, Supertrend, Donchian, ADX.
- Nine backtest strategies plus walk-forward in `backtest_service.py`: RSI, Bollinger, MACD, EMA cross, Supertrend, Donchian, RSI pullback, Keltner breakout, triple EMA. Metrics include win rate, return, Sharpe, Calmar, drawdown, profit factor, and expectancy, with percentage commission and slippage.
- Yahoo Finance chart quotes and daily or hourly history. A 60-second screener cache and retries live in the screener provider.
- Errors on the newer tools use a structured envelope. The project is Python-only. The official package is `tradingview-mcp-server` on PyPI. There is no official npm package; a root `package.json` on a copy of this repo is a known malware pattern and is still gitignored.

## What it does not do

- It is not a multi-user SaaS, and it has no accounts, watchlists, alerts, or billing.
- Yahoo and TradingView screener calls are unofficial. They are not an NSE or BSE license, and India quotes are delayed. Intraday history is only present when that response actually contains bars.
- There is no bulk-deal, block-deal, or corporate-announcement client.
- Backtests fill on the signal bar's close. That is earlier than a next-bar-open fill. Costs are a single percent, not an Indian statutory schedule. Sharpe defaults are US-market (252 sessions, 4% risk-free) unless the caller overrides them.
- Hourly and daily are the only backtest intervals. One-minute through 30-minute scans are outside the engine.
- Paper trading and live broker execution are not implemented in the engine. Live trading stays disabled in this application.
- Python 3.14 cannot install the full MCP stack. This machine has 3.14. The SaaS imports the indicator, backtest, and Yahoo modules, which do not need `pandas` or `mcp`. Running `tradingview-mcp` itself still wants Python 3.10–3.13.

## SaaS layout

```
src/tradingview_mcp/          existing engine, unchanged except Yahoo symbol encoding
apps/api/                     FastAPI application
apps/web/                     Next.js terminal
docs/                         this note and the runbook
docker-compose.saas.yml       Postgres, Redis, API, web
```

`M&M.NS` is percent-encoded in Yahoo chart URLs. Dots and carets are left as-is. That is the only engine change.

The API owns users, watchlists, holdings, alerts, paper orders, strategies, and audit logs in SQLite or PostgreSQL. Redis is reserved for a later shared cache; the API currently uses a short in-process TTL so a missing Redis does not block local use. APScheduler runs inside the API process when `SCHEDULER_ENABLED=true`. The website being open does not run scans.

Market calculations that must be reproducible — breakouts, 52-week distance, index windows, costs, alert cooldowns — live in `apps/api/app/market/` and call the engine's indicator functions. The assistant is allowed to explain those results. It is not allowed to invent prices. An OpenAI-compatible model is used only when `OPENAI_API_KEY` is set, and only to rephrase tool JSON.

## Providers

| Need | Adapter | Status |
| --- | --- | --- |
| Quotes and OHLCV | Yahoo chart API via the engine | Live path. Delayed, unofficial. |
| Symbol search | Engine NSE/BSE coin lists plus the NIFTY 50 snapshot | Local files. The snapshot is dated 2026-06-11, not a live index feed. |
| Screeners | `tradingview-screener` | Left on the MCP server. The SaaS scan uses candles and engine indicators so it does not depend on that package. |
| Bulk, block, announcements | Public NSE JSON the exchange site calls | Best-effort. Failures return an unavailable state and the official URL. BSE pages are linked, not parsed. |
| Demo | `DATA_MODE=demo` | Synthetic series, labeled on every payload. |

Do not ship this against Yahoo or TradingView as a paid data product without a license. An official NSE or BSE vendor slots in behind `app/providers` without a UI rewrite.

## Plans

Limits are enforced in `app/limits.py`. Free includes a small number of watchlists, end-of-day scans, and one saved strategy. Backtests, the assistant, and intraday scans start on Pro. Walk-forward starts on Pro. Premium raises the same quotas. No payment provider is wired; an admin can change a plan. That is intentional until the research loop is trustworthy.

## Safety

Secrets stay in `.env`. Live broker execution refuses to boot if enabled. Paper fills are labeled paper, use the latest quote plus slippage and an approximate delivery-cost model, and do not open a broker session. Alerts ignore stale quotes. A repeated fingerprint stays silent until the cooldown ends, then re-arms; a cleared condition re-arms immediately.
