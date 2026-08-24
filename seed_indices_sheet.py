"""One-off seed script: writes the sector index universe to the 'Indices' worksheet.

Run again any time the index list in src/data/indices.py changes — it
overwrites the worksheet in place rather than appending.
"""

from src.data.indices import SECTOR_INDICES
from src.integrations.google_sheets import get_or_create_worksheet, get_spreadsheet

WORKSHEET_TITLE = "Indices"


def main():
    spreadsheet = get_spreadsheet()
    worksheet = get_or_create_worksheet(
        spreadsheet, WORKSHEET_TITLE, rows=len(SECTOR_INDICES) + 1, cols=1
    )

    worksheet.clear()
    rows = [["Index Name"]] + [[name] for name in SECTOR_INDICES]
    worksheet.update(values=rows, range_name="A1")

    print(f"Wrote {len(SECTOR_INDICES)} indices to '{WORKSHEET_TITLE}'")


if __name__ == "__main__":
    main()
