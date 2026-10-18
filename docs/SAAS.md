# Running the Indian market terminal

The MCP server and this terminal are different processes. Leave `src/tradingview_mcp` in place. Commands below assume the repository root.

## API

Python 3.14 can run the API. The original `tradingview-mcp` console script still needs Python 3.10–3.13 because of its pinned native dependencies.

```powershell
cd d:\xampp\htdocs\trv
py -3 -m venv apps\api\.venv
apps\api\.venv\Scripts\python -m pip install -r apps\api\requirements.txt
$env:PYTHONPATH = "d:\xampp\htdocs\trv\src"
cd apps\api
..\.venv\Scripts\python -m pytest
..\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

The venv lives in `apps/api/.venv`, so from `apps/api` the interpreter is `.venv\Scripts\python`.

Copy `.env.example` to `.env` only for values you use. The API starts on SQLite at `data/bazaar.db` with `DATA_MODE=live`. Set `DATA_MODE=demo` to force synthetic prices. Demo mode is labeled in the API and in the banner. It never fills in for a failed live request.

`SECRET_KEY` must be changed before `APP_ENV=production`. `LIVE_TRADING_ENABLED=true` aborts startup.

In development, registration returns `verification_token` and password reset returns `reset_token` because SMTP is optional. Production does not return those tokens. Set `SMTP_*` and `TELEGRAM_BOT_TOKEN` to actually deliver them. Set `OPENAI_API_KEY` only if the assistant should rephrase tool output. Without it, the assistant still returns the tool sections.

Create an admin with `ADMIN_EMAIL` and `ADMIN_PASSWORD`. The admin can change plans at `PATCH /api/v1/admin/users/{id}/plan`. There is no card processor.

Health: `GET http://127.0.0.1:8000/api/v1/health`

Provider status: `GET http://127.0.0.1:8000/api/v1/market/status` (authenticated)

## Web

```powershell
cd d:\xampp\htdocs\trv\apps\web
npm install
npm run dev
```

Open http://localhost:3000. The browser calls `NEXT_PUBLIC_API_URL` (default `http://127.0.0.1:8000`).

## Tests

```powershell
cd d:\xampp\htdocs\trv\apps\api
.venv\Scripts\python -m pytest
```

Scanner, 52-week, index threshold, cooldown, costs, registration, and watchlist isolation do not call the network. A live quote check is manual: `GET /api/v1/market/quote?symbol=RELIANCE` after login.

Engine encoding test, from the repo root once `httpx` is importable or by pointing pytest at the file with the API venv:

```powershell
$env:PYTHONPATH = "d:\xampp\htdocs\trv\src"
apps\api\.venv\Scripts\python -m pytest tests\unit\test_yahoo_symbol_encoding.py
```

## Docker

`docker-compose.saas.yml` starts PostgreSQL, Redis, the API, and the web app. Redis is not required for the current cache. The original `docker-compose.yml` still runs only the MCP server.

```powershell
docker compose -f docker-compose.saas.yml up --build
```

Set a real `SECRET_KEY` in that file before any shared deployment.

## Data limits

- Yahoo Finance is unofficial and typically delayed. The UI says so.
- NIFTY 50 names are a 2026-06-11 snapshot, not a live membership file.
- Session status ignores exchange holidays.
- 52-week distance on the Highs page is the prior 252 daily sessions, excluding the latest bar. Fewer bars are marked partial.
- The dashboard's 52-week distances use Yahoo's own high and low fields and are labeled that way.
- Bulk and block rows appear only when NSE returns them. A blocked client shows the official links and an empty list.
- Backtests reuse the engine. Fills are on the signal close, costs are an approximation of delivery charges allocated across both sides, and a good history is not a forecast.
- Intraday alerts are "close confirmed" only for the last candle the provider returned. That is not the same as an end-of-day confirmation.
- Paper trading is simulated. Broker execution is not implemented.

## Original engine

```powershell
uv run tradingview-mcp
```

Use Python 3.13 for that command. It keeps the 37 MCP tools, including NSE and BSE screeners, available to an MCP client.
