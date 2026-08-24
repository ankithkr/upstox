"""Minimal Flask app to complete the Upstox OAuth login flow.

Run this, open http://localhost:<PORT>/ in a browser, log in with
Upstox, and the resulting access token is saved to UPSTOX_TOKEN_FILE
for the rest of the app to use.
"""

from flask import Flask, redirect, request

from src.config import FLASK_SECRET_KEY, PORT
from src.integrations.upstox_auth import build_login_url, exchange_code_for_token, save_token

app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY


@app.route("/")
def login():
    return redirect(build_login_url())


@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return f"Authorization failed: {request.args.get('error', 'unknown error')}", 400

    token_data = exchange_code_for_token(code)
    save_token(token_data)

    return "Upstox login successful. You can close this tab."


if __name__ == "__main__":
    app.run(port=PORT)
