import json

import pytest

from app.auth import load_access_token


def test_loads_access_token_from_file(tmp_path, monkeypatch):
    token_file = tmp_path / "token.json"
    token_file.write_text(json.dumps({"access_token": "abc123"}))
    monkeypatch.setenv("UPSTOX_TOKEN_FILE", str(token_file))

    assert load_access_token() == "abc123"


def test_missing_file_raises_clear_error(tmp_path, monkeypatch):
    monkeypatch.setenv("UPSTOX_TOKEN_FILE", str(tmp_path / "missing.json"))

    with pytest.raises(RuntimeError, match="not found"):
        load_access_token()


def test_missing_access_token_field_raises_clear_error(tmp_path, monkeypatch):
    token_file = tmp_path / "token.json"
    token_file.write_text(json.dumps({"user_id": "32AS4M"}))
    monkeypatch.setenv("UPSTOX_TOKEN_FILE", str(token_file))

    with pytest.raises(RuntimeError, match="access_token"):
        load_access_token()
