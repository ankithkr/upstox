RED = {"red": 0.96, "green": 0.49, "blue": 0.49}
NEUTRAL = {"red": 0.96, "green": 0.96, "blue": 0.96}
GREEN = {"red": 0.42, "green": 0.73, "blue": 0.48}


def _existing_rule_count(spreadsheet, sheet_id) -> int:
    metadata = spreadsheet.fetch_sheet_metadata()
    for sheet in metadata["sheets"]:
        if sheet["properties"]["sheetId"] == sheet_id:
            return len(sheet.get("conditionalFormats", []))
    return 0


def replace_percent_change_heatmap(
    spreadsheet, sheet_id, ranges, min_value=-3, max_value=3
) -> None:
    """Replace any existing conditional format rules on a sheet with a
    single red-gray-green gradient over the given ranges.

    `ranges` is a list of Sheets API GridRange dicts (0-indexed,
    end-exclusive) covering the % change column(s) to color.
    """
    existing = _existing_rule_count(spreadsheet, sheet_id)
    requests = [
        {"deleteConditionalFormatRule": {"sheetId": sheet_id, "index": 0}}
        for _ in range(existing)
    ]

    requests.append(
        {
            "addConditionalFormatRule": {
                "index": 0,
                "rule": {
                    "ranges": ranges,
                    "gradientRule": {
                        "minpoint": {
                            "type": "NUMBER",
                            "value": str(min_value),
                            "color": RED,
                        },
                        "midpoint": {
                            "type": "NUMBER",
                            "value": "0",
                            "color": NEUTRAL,
                        },
                        "maxpoint": {
                            "type": "NUMBER",
                            "value": str(max_value),
                            "color": GREEN,
                        },
                    },
                },
            }
        }
    )

    spreadsheet.batch_update({"requests": requests})
