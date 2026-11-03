import httpx
import pytest

from app.feed_client import AUTHORIZE_URL, get_authorized_ws_url


@pytest.mark.asyncio
async def test_get_authorized_ws_url_sends_bearer_token_and_parses_response():
    captured_request: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_request["url"] = str(request.url)
        captured_request["headers"] = request.headers
        return httpx.Response(
            200,
            json={"status": "success", "data": {"authorized_redirect_uri": "wss://example.com/feed"}},
        )

    transport = httpx.MockTransport(handler)

    import app.feed_client as feed_client_module

    original_client = httpx.AsyncClient
    httpx.AsyncClient = lambda **kwargs: original_client(transport=transport)
    try:
        url = await get_authorized_ws_url("test-token")
    finally:
        httpx.AsyncClient = original_client

    assert url == "wss://example.com/feed"
    assert captured_request["url"] == AUTHORIZE_URL
    assert captured_request["headers"]["authorization"] == "Bearer test-token"
    assert captured_request["headers"]["accept"] == "application/json"
