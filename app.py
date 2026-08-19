import json
import os

import requests
from dotenv import load_dotenv
from flask import Flask, redirect, request

from instruments import resolve_instrument_key

load_dotenv()

UPSTOX_API_KEY = os.environ["UPSTOX_API_KEY"]
UPSTOX_API_SECRET = os.environ["UPSTOX_API_SECRET"]
UPSTOX_REDIRECT_URI = os.environ["UPSTOX_REDIRECT_URI"]

AUTHORIZATION_URL = "https://api.upstox.com/v2/login/authorization/dialog"
TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"
LTP_URL = "https://api.upstox.com/v3/market-quote/ltp"
TOKEN_FILE = "token.json"

STOCK_SYMBOL = "HNGSNGBEES"  # hardcoded for now

app = Flask(__name__)


@app.route("/")
def index():
    return '<a href="/login">Login with Upstox</a>'


@app.route("/login")
def login():
    # Step 1: send the customer to the Upstox login page
    params = {
        "response_type": "code",
        "client_id": UPSTOX_API_KEY,
        "redirect_uri": UPSTOX_REDIRECT_URI,
    }
    auth_url = f"{AUTHORIZATION_URL}?{requests.compat.urlencode(params)}"
    return redirect(auth_url)


@app.route("/callback")
def callback():
    # Step 2: Upstox redirects here with the authorization code
    error = request.args.get("error")
    if error:
        return f"Authorization failed: {error}", 400

    code = request.args.get("code")
    if not code:
        return "Missing authorization code", 400

    # Step 3: exchange the code for an access token
    response = requests.post(
        TOKEN_URL,
        headers={
            "accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "code": code,
            "client_id": UPSTOX_API_KEY,
            "client_secret": UPSTOX_API_SECRET,
            "redirect_uri": UPSTOX_REDIRECT_URI,
            "grant_type": "authorization_code",
        },
    )

    if not response.ok:
        return f"Token exchange failed: {response.status_code} {response.text}", 502

    token_data = response.json()

    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f, indent=2)

    return token_data


@app.route("/ltp")
def ltp():
    if not os.path.exists(TOKEN_FILE):
        return "No access token found, log in via /login first", 401

    with open(TOKEN_FILE) as f:
        access_token = json.load(f)["access_token"]

    instrument_key = resolve_instrument_key(STOCK_SYMBOL)

    response = requests.get(
        LTP_URL,
        params={"instrument_key": instrument_key},
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
        },
    )

    if not response.ok:
        return f"LTP request failed: {response.status_code} {response.text}", 502

    return response.json()


if __name__ == "__main__":
    app.run(port=int(os.environ.get("PORT", 5000)), debug=True)
