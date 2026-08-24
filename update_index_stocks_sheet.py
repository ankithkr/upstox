"""Populate a worksheet per index with its constituent stocks' live
% change from Upstox, heatmapped the same way as the Indices sheet.

For each index in INDEX_CONSTITUENTS, creates/updates a worksheet
named exactly after the index (e.g. "NIFTY AUTO") with
Symbol | % Change | LTP. Safe to rerun.
"""

import time

import gspread

from src.calculations.percentage import pct_change
from src.data.stocks import INDEX_CONSTITUENTS
from src.integrations.google_sheets import get_or_create_worksheet, get_spreadsheet
from src.integrations.sheet_heatmap import replace_percent_change_heatmap
from src.integrations.upstox_instruments import build_equity_symbol_index, load_instrument_master
from src.integrations.upstox_quotes import get_quotes

HEADER = ["Symbol", "% Change", "LTP"]

# Each index does 3 Sheets API writes (clear, values, heatmap). Google's
# default write quota is 60/minute per user, so pause between indices
# to stay under it, and back off if a burst still trips the quota.
SECONDS_BETWEEN_INDICES = 3
RATE_LIMIT_RETRIES = 5
RATE_LIMIT_BACKOFF_SECONDS = 20


def _is_rate_limit_error(error: gspread.exceptions.APIError) -> bool:
    return error.response.status_code == 429


def update_index_sheet(spreadsheet, index_name, symbols, symbol_index):
    instrument_keys = [symbol_index[symbol] for symbol in symbols]
    quotes = get_quotes(instrument_keys)

    rows = []
    for symbol, instrument_key in zip(symbols, instrument_keys):
        quote = quotes[instrument_key]
        change = pct_change(quote["last_price"], quote["prev_close"])
        rows.append([symbol, round(change, 2), quote["last_price"]])

    worksheet = get_or_create_worksheet(
        spreadsheet, index_name, rows=len(rows) + 1, cols=len(HEADER)
    )
    worksheet.clear()
    worksheet.update(values=[HEADER] + rows, range_name="A1")

    gradient_range = [
        {
            "sheetId": worksheet.id,
            "startRowIndex": 1,
            "endRowIndex": 1 + len(rows),
            "startColumnIndex": 1,
            "endColumnIndex": 2,
        }
    ]
    replace_percent_change_heatmap(spreadsheet, worksheet.id, gradient_range)

    print(f"Updated {len(rows)} stocks in '{index_name}'")


def main():
    spreadsheet = get_spreadsheet()
    symbol_index = build_equity_symbol_index(load_instrument_master())

    for index_name, symbols in INDEX_CONSTITUENTS.items():
        for attempt in range(1, RATE_LIMIT_RETRIES + 1):
            try:
                update_index_sheet(spreadsheet, index_name, symbols, symbol_index)
                break
            except gspread.exceptions.APIError as error:
                if not _is_rate_limit_error(error) or attempt == RATE_LIMIT_RETRIES:
                    raise
                print(f"Rate limited on '{index_name}', retrying in {RATE_LIMIT_BACKOFF_SECONDS}s...")
                time.sleep(RATE_LIMIT_BACKOFF_SECONDS)

        time.sleep(SECONDS_BETWEEN_INDICES)


if __name__ == "__main__":
    main()
