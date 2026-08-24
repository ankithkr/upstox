"""Refresh the 'Indices' worksheet with live % change from Upstox,
apply a heatmap color scale next to each index name, and surface
NIFTY 50 above the header, highlighted.

Run any time during or after market hours to pull the latest quotes.
Safe to rerun — it overwrites values and replaces the conditional
formatting rule rather than stacking duplicates.
"""

from src.calculations.percentage import pct_change
from src.data.indices import (
    NIFTY_50_INSTRUMENT_KEY,
    NIFTY_50_NAME,
    SECTOR_INDEX_INSTRUMENT_KEYS,
    SECTOR_INDICES,
)
from src.integrations.google_sheets import get_spreadsheet
from src.integrations.sheet_heatmap import replace_percent_change_heatmap
from src.integrations.upstox_quotes import get_quotes

WORKSHEET_TITLE = "Indices"
HEADER = ["Index Name", "% Change", "LTP"]

NIFTY_50_CHANGE_BG = {"red": 1.0, "green": 0.84, "blue": 0.40}


def build_rows():
    instrument_keys = [SECTOR_INDEX_INSTRUMENT_KEYS[name] for name in SECTOR_INDICES]
    quotes = get_quotes(instrument_keys + [NIFTY_50_INSTRUMENT_KEY])

    def row_for(name, instrument_key):
        quote = quotes[instrument_key]
        change = pct_change(quote["last_price"], quote["prev_close"])
        return [name, round(change, 2), quote["last_price"]]

    sector_rows = [row_for(name, SECTOR_INDEX_INSTRUMENT_KEYS[name]) for name in SECTOR_INDICES]
    nifty_50_row = row_for(NIFTY_50_NAME, NIFTY_50_INSTRUMENT_KEY)

    return sector_rows, nifty_50_row


def highlight_nifty_50(spreadsheet, sheet_id):
    spreadsheet.batch_update(
        {
            "requests": [
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 0,
                            "endRowIndex": 1,
                            "startColumnIndex": 1,
                            "endColumnIndex": 2,
                        },
                        "cell": {
                            "userEnteredFormat": {"backgroundColor": NIFTY_50_CHANGE_BG}
                        },
                        "fields": "userEnteredFormat(backgroundColor)",
                    }
                }
            ]
        }
    )


def main():
    spreadsheet = get_spreadsheet()
    worksheet = spreadsheet.worksheet(WORKSHEET_TITLE)

    sector_rows, nifty_50_row = build_rows()
    worksheet.clear()
    worksheet.update(values=[nifty_50_row, HEADER] + sector_rows, range_name="A1")

    # Row 0 is NIFTY 50, row 1 is the header, sector rows start at row 2.
    gradient_range = [
        {
            "sheetId": worksheet.id,
            "startRowIndex": 2,
            "endRowIndex": 2 + len(sector_rows),
            "startColumnIndex": 1,
            "endColumnIndex": 2,
        }
    ]
    replace_percent_change_heatmap(spreadsheet, worksheet.id, gradient_range)
    highlight_nifty_50(spreadsheet, worksheet.id)

    print(f"Updated {len(sector_rows)} sector rows in '{WORKSHEET_TITLE}' (NIFTY 50 above header)")


if __name__ == "__main__":
    main()
