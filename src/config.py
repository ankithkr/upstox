import os

from dotenv import load_dotenv

load_dotenv()

UPSTOX_API_KEY = os.getenv("UPSTOX_API_KEY")
UPSTOX_API_SECRET = os.getenv("UPSTOX_API_SECRET")
UPSTOX_REDIRECT_URI = os.getenv("UPSTOX_REDIRECT_URI", "http://localhost:5000/callback")
UPSTOX_TOKEN_FILE = os.getenv("UPSTOX_TOKEN_FILE", "token.json")
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY")
PORT = int(os.getenv("PORT", "5000"))

GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "creds.json")
GOOGLE_TOKEN_FILE = os.getenv("GOOGLE_TOKEN_FILE", "token_google.json")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
