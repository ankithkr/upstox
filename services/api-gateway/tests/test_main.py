from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_trades_returns_empty_list_when_supabase_unavailable(monkeypatch):
    import app.queries as queries

    monkeypatch.setattr(queries, "fetch_trades", lambda **kw: [])
    resp = client.get("/trades")
    assert resp.status_code == 200
    assert resp.json() == []


def test_trades_shapes_rows_into_the_trade_model(monkeypatch):
    import app.queries as queries

    row = {
        "id": "trd-1", "order_id": "ord-1", "symbol": "TCS", "direction": "LONG",
        "status": "CLOSED", "qty": 10, "entry_price": 100.0, "entry_time": "2026-01-02T09:45:00+05:30",
        "exit_price": 103.0, "exit_time": "2026-01-02T10:00:00+05:30",
        "gross_pnl": 30.0, "charges": 5.0, "net_pnl": 25.0, "r_multiple": 1.25,
    }
    monkeypatch.setattr(queries, "fetch_trades", lambda **kw: [row])
    resp = client.get("/trades")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["symbol"] == "TCS"
    assert body[0]["net_pnl"] == 25.0


def test_positions_delegates_to_open_status(monkeypatch):
    import app.queries as queries

    captured = {}

    def fake_fetch_positions():
        captured["called"] = True
        return []

    monkeypatch.setattr(queries, "fetch_positions", fake_fetch_positions)
    resp = client.get("/positions")
    assert resp.status_code == 200
    assert captured.get("called") is True


def test_equity_curve(monkeypatch):
    import app.queries as queries

    rows = [{"ts": "2026-01-02T15:30:00+05:30", "equity": 100500.0, "cash": 100500.0, "open_risk": 0.0}]
    monkeypatch.setattr(queries, "fetch_equity_curve", lambda **kw: rows)
    resp = client.get("/equity-curve")
    assert resp.status_code == 200
    assert resp.json()[0]["equity"] == 100500.0


def test_strategy_config_returns_null_when_nothing_published(monkeypatch):
    import app.queries as queries

    monkeypatch.setattr(queries, "fetch_latest_strategy_config", lambda: None)
    resp = client.get("/strategy-config")
    assert resp.status_code == 200
    assert resp.json() is None


def test_strategy_config_returns_the_published_row(monkeypatch):
    import app.queries as queries

    row = {"version": "v2", "params": {"nifty_band_pct": 0.3}, "created_at": "2026-01-02T08:00:00+05:30"}
    monkeypatch.setattr(queries, "fetch_latest_strategy_config", lambda: row)
    resp = client.get("/strategy-config")
    assert resp.status_code == 200
    assert resp.json()["version"] == "v2"
