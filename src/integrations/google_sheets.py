import gspread

from src.config import GOOGLE_CREDENTIALS_FILE, GOOGLE_SHEET_ID, GOOGLE_TOKEN_FILE

SCOPES = ("https://www.googleapis.com/auth/spreadsheets",)


def get_client():
    return gspread.oauth(
        credentials_filename=GOOGLE_CREDENTIALS_FILE,
        authorized_user_filename=GOOGLE_TOKEN_FILE,
        scopes=SCOPES,
    )


def get_spreadsheet():
    if not GOOGLE_SHEET_ID:
        raise RuntimeError("GOOGLE_SHEET_ID is not set in .env")
    return get_client().open_by_key(GOOGLE_SHEET_ID)


def get_or_create_worksheet(spreadsheet, title, rows, cols):
    try:
        return spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=title, rows=rows, cols=cols)
