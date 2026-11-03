"""The "Connect Upstox" flow: the dashboard links here instead of running
a separate local script. api-gateway is the one service with a stable,
reachable URL (locally or deployed), so it owns the OAuth redirect/
callback; the resulting token is written to Supabase's upstox_tokens
table, which data-engine reads instead of a locally mounted file.

This does NOT get around the daily-login requirement (Upstox/SEBI still
require a fresh login each trading day) - it just makes that daily
ritual one click on the dashboard instead of a separate script.
"""

from __future__ import annotations

import logging
import os
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

from shared.db import get_supabase

log = logging.getLogger("api-gateway.upstox_auth")

AUTH_URL = "https://api.upstox.com/v2/login/authorization/dialog"
TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"

router = APIRouter(prefix="/auth/upstox", tags=["upstox-auth"])


def _api_key() -> str:
    return os.environ["UPSTOX_API_KEY"]


def _api_secret() -> str:
    return os.environ["UPSTOX_API_SECRET"]


def _redirect_uri() -> str:
    return os.environ.get("UPSTOX_REDIRECT_URI", "http://localhost:8000/auth/upstox/callback")


@router.get("/login")
async def login() -> RedirectResponse:
    params = {"response_type": "code", "client_id": _api_key(), "redirect_uri": _redirect_uri()}
    return RedirectResponse(f"{AUTH_URL}?{urlencode(params)}")


@router.get("/callback", response_class=HTMLResponse)
async def callback(code: str | None = None, error: str | None = None) -> str:
    if not code:
        return f"<p>Upstox login failed: {error or 'unknown error'}</p>"

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            TOKEN_URL,
            headers={"accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
            data={
                "code": code,
                "client_id": _api_key(),
                "client_secret": _api_secret(),
                "redirect_uri": _redirect_uri(),
                "grant_type": "authorization_code",
            },
        )
        resp.raise_for_status()
        access_token = resp.json()["access_token"]

    try:
        get_supabase().table("upstox_tokens").insert({"access_token": access_token}).execute()
    except Exception:
        log.warning("could not write the fresh Upstox token to Supabase", exc_info=True)
        return "<p>Logged in with Upstox, but saving the token to Supabase failed - check api-gateway's logs.</p>"

    return "<p>Upstox login successful. You can close this tab.</p>"
