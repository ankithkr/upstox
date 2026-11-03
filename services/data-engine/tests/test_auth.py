import json

import pytest

from app.auth import load_access_token


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


def test_prefers_the_supabase_token_when_available(monkeypatch, tmp_path):
    import app.auth as auth_module

    monkeypatch.setattr(auth_module, "get_supabase", lambda: _FakeClient([{"access_token": "from-supabase"}]))
    # even with a valid local file present, Supabase wins
    token_file = tmp_path / "token.json"
    token_file.write_text(json.dumps({"access_token": "from-file"}))
    monkeypatch.setenv("UPSTOX_TOKEN_FILE", str(token_file))

    assert load_access_token() == "from-supabase"


def test_falls_back_to_file_when_supabase_has_no_rows(monkeypatch, tmp_path):
    import app.auth as auth_module

    monkeypatch.setattr(auth_module, "get_supabase", lambda: _FakeClient([]))
    token_file = tmp_path / "token.json"
    token_file.write_text(json.dumps({"access_token": "from-file"}))
    monkeypatch.setenv("UPSTOX_TOKEN_FILE", str(token_file))

    assert load_access_token() == "from-file"


def test_falls_back_to_file_when_supabase_call_raises(monkeypatch, tmp_path):
    import app.auth as auth_module

    def _raise():
        raise RuntimeError("network error")

    monkeypatch.setattr(auth_module, "get_supabase", _raise)
    token_file = tmp_path / "token.json"
    token_file.write_text(json.dumps({"access_token": "from-file"}))
    monkeypatch.setenv("UPSTOX_TOKEN_FILE", str(token_file))

    assert load_access_token() == "from-file"


def test_missing_file_raises_clear_error_when_supabase_also_empty(monkeypatch, tmp_path):
    import app.auth as auth_module

    monkeypatch.setattr(auth_module, "get_supabase", lambda: _FakeClient([]))
    monkeypatch.setenv("UPSTOX_TOKEN_FILE", str(tmp_path / "missing.json"))

    with pytest.raises(RuntimeError, match="No Upstox token"):
        load_access_token()


def test_missing_access_token_field_in_file_raises_clear_error(monkeypatch, tmp_path):
    import app.auth as auth_module

    monkeypatch.setattr(auth_module, "get_supabase", lambda: _FakeClient([]))
    token_file = tmp_path / "token.json"
    token_file.write_text(json.dumps({"user_id": "32AS4M"}))
    monkeypatch.setenv("UPSTOX_TOKEN_FILE", str(token_file))

    with pytest.raises(RuntimeError, match="access_token"):
        load_access_token()
