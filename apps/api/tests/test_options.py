def _contract(key: str, symbol: str) -> dict:
    return {
        "expiry": "2026-10-27",
        "instrument_key": key,
        "trading_symbol": symbol,
        "lot_size": 65,
        "freeze_quantity": 3510,
    }


def test_chain_uses_upstox_rows_and_does_not_swap_midcap(monkeypatch):
    from app.services import options

    options._CONTRACTS.clear()
    options._CHAINS.clear()
    monkeypatch.setattr(
        options,
        "fetch_contracts",
        lambda _key: [
            _contract("NSE_FO|1", "NIFTY 23000 CE 27 OCT 26"),
            _contract("NSE_FO|2", "NIFTY 23000 PE 27 OCT 26"),
        ],
    )
    monkeypatch.setattr(
        options,
        "fetch_chain",
        lambda _key, expiry: {
            "rows": [
                {
                    "expiry": expiry,
                    "strike_price": 23000,
                    "underlying_spot_price": 22888.95,
                    "call_options": {
                        "instrument_key": "NSE_FO|1",
                        "market_data": {"ltp": 120.5, "oi": 10, "close_price": 100, "prev_oi": 8},
                        "option_greeks": {"iv": 12.5, "delta": 0.5, "theta": -4, "gamma": 0.001},
                    },
                    "put_options": {
                        "instrument_key": "NSE_FO|2",
                        "market_data": {"ltp": 40},
                        "option_greeks": {},
                    },
                }
            ]
        },
    )
    body = options.build_chain("nifty50", "2026-10-27")
    assert body["available"] is True
    assert body["spot"] == 22888.95
    assert body["lot_size"] == 65
    assert body["rows"][0]["call"]["ltp"] == 120.5
    assert body["rows"][0]["call"]["trading_symbol"] == "NIFTY 23000 CE 27 OCT 26"
    assert body["rows"][0]["put"]["delta"] is None
    parsed = options.parse_trading_symbol("NIFTY 23000 CE 27 OCT 26")
    assert parsed["index"] == "nifty50"
    assert parsed["expiry"] == "2026-10-27"

    missing = options.build_chain("niftymid")
    assert missing["available"] is False
    assert missing["rows"] == []


def test_paper_option_order_fills_at_chain_premium(client, monkeypatch):
    from app.services import options

    monkeypatch.setattr(
        options,
        "quote_contract",
        lambda *_args, **_kwargs: {
            "trading_symbol": "NIFTY 23000 CE 27 OCT 26",
            "ltp": 100.0,
            "lot_size": 65,
            "max_lots": 54,
            "expiry": "2026-10-27",
            "as_of": "2026-10-19T16:00:00+00:00",
            "quote_stale": True,
        },
    )
    registered = client.post(
        "/api/v1/auth/register",
        json={"email": "options@example.com", "password": "a-long-password", "name": "Options"},
    )
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    bought = client.post(
        "/api/v1/paper/option-orders",
        json={"index": "nifty50", "expiry": "2026-10-27", "strike": 23000, "right": "CE", "side": "buy", "lots": 1},
        headers=headers,
    )
    assert bought.status_code == 200, bought.text
    body = bought.json()
    assert body["symbol"] == "NIFTY 23000 CE 27 OCT 26"
    assert body["quantity"] == 65
    assert body["quote_price"] == 100
    assert body["provider"] == "upstox"
    assert body["live_trading_enabled"] is False
    assert body["position_quantity"] == 65
    assert body["cash"] < 1_000_000

    sold = client.post(
        "/api/v1/paper/option-orders",
        json={"index": "nifty50", "expiry": "2026-10-27", "strike": 23000, "right": "CE", "side": "sell", "lots": 1},
        headers=headers,
    )
    assert sold.status_code == 200, sold.text
    assert sold.json()["position_quantity"] == 0

    naked = client.post(
        "/api/v1/paper/option-orders",
        json={"index": "nifty50", "expiry": "2026-10-27", "strike": 23000, "right": "CE", "side": "sell", "lots": 1},
        headers=headers,
    )
    assert naked.status_code == 400
