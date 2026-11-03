from app.equity import latest_equity


class _FakeResponse:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def select(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def execute(self):
        return _FakeResponse(self._rows)


class _FakeClient:
    def __init__(self, rows):
        self._rows = rows

    def table(self, _name):
        return _FakeQuery(self._rows)


def test_falls_back_to_default_when_supabase_is_not_configured(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    import shared.db

    shared.db.get_supabase.cache_clear()
    assert latest_equity(default=100_000.0) == 100_000.0


def test_returns_latest_snapshot_when_available(monkeypatch):
    import app.equity as equity_module

    monkeypatch.setattr(equity_module, "get_supabase", lambda: _FakeClient([{"equity": 105234.5}]))
    assert latest_equity(default=100_000.0) == 105234.5


def test_falls_back_when_no_rows_exist(monkeypatch):
    import app.equity as equity_module

    monkeypatch.setattr(equity_module, "get_supabase", lambda: _FakeClient([]))
    assert latest_equity(default=100_000.0) == 100_000.0


def test_falls_back_when_supabase_call_raises(monkeypatch):
    import app.equity as equity_module

    def _raise():
        raise RuntimeError("network error")

    monkeypatch.setattr(equity_module, "get_supabase", _raise)
    assert latest_equity(default=100_000.0) == 100_000.0
