import httpx
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, follow_redirects=False)


def test_login_redirects_to_upstox_with_correct_params(monkeypatch):
    monkeypatch.setenv("UPSTOX_API_KEY", "test-key")
    monkeypatch.setenv("UPSTOX_REDIRECT_URI", "http://localhost:8000/auth/upstox/callback")

    resp = client.get("/auth/upstox/login")
    assert resp.status_code in (302, 307)
    location = resp.headers["location"]
    assert location.startswith("https://api.upstox.com/v2/login/authorization/dialog")
    assert "client_id=test-key" in location
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Fauth%2Fupstox%2Fcallback" in location


def test_callback_without_code_returns_error_page():
    resp = client.get("/auth/upstox/callback", params={"error": "access_denied"})
    assert resp.status_code == 200
    assert "access_denied" in resp.text


def test_callback_exchanges_code_and_saves_token(monkeypatch):
    import app.upstox_auth as upstox_auth_module

    monkeypatch.setenv("UPSTOX_API_KEY", "test-key")
    monkeypatch.setenv("UPSTOX_API_SECRET", "test-secret")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/login/authorization/token"
        return httpx.Response(200, json={"access_token": "fresh-token-123"})

    original_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: original_client(transport=httpx.MockTransport(handler)))

    saved = {}

    class _FakeQuery:
        def insert(self, data):
            saved.update(data)
            return self

        def execute(self):
            return None

    class _FakeClient:
        def table(self, name):
            assert name == "upstox_tokens"
            return _FakeQuery()

    monkeypatch.setattr(upstox_auth_module, "get_supabase", lambda: _FakeClient())

    resp = client.get("/auth/upstox/callback", params={"code": "auth-code"})
    assert resp.status_code == 200
    assert "successful" in resp.text
    assert saved == {"access_token": "fresh-token-123"}


def test_callback_reports_when_supabase_write_fails(monkeypatch):
    import app.upstox_auth as upstox_auth_module

    monkeypatch.setenv("UPSTOX_API_KEY", "test-key")
    monkeypatch.setenv("UPSTOX_API_SECRET", "test-secret")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": "fresh-token-123"})

    original_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: original_client(transport=httpx.MockTransport(handler)))

    def _raise():
        raise RuntimeError("supabase down")

    monkeypatch.setattr(upstox_auth_module, "get_supabase", _raise)

    resp = client.get("/auth/upstox/callback", params={"code": "auth-code"})
    assert resp.status_code == 200
    assert "saving the token" in resp.text
