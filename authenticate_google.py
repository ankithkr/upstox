"""Run once to complete the Google OAuth flow and verify sheet access.

Opens a browser for consent (using creds.json), caches the resulting
token to GOOGLE_TOKEN_FILE, then confirms it can see the target
spreadsheet named by GOOGLE_SHEET_ID in .env.
"""

from src.integrations.google_sheets import get_spreadsheet


def main():
    sh = get_spreadsheet()
    print(f"Connected to spreadsheet: {sh.title}")
    print("Worksheets:", [ws.title for ws in sh.worksheets()])


if __name__ == "__main__":
    main()
