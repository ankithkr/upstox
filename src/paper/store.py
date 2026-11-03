"""Where paper trades live. Google Sheets is the real store; LocalStore is
the same interface on a JSON file, for replay runs and offline testing.

Trades are upserted by trade_id, so re-writing the same day every tick
updates rows in place instead of duplicating them.
"""

import json
from pathlib import Path

from src.paper import config
from src.paper.engine import TRADE_COLUMNS
from src.paper.summary import DAILY_HEADER, account_summary, daily_table

_NUMERIC = {
    "sector_change", "stock_change", "opening_high", "opening_low", "entry_price",
    "stop_loss", "target", "qty", "position_value", "risk_amount", "exit_price",
    "last_price", "gross_pnl", "charges", "net_pnl", "r_multiple", "hold_minutes",
}  # fmt: skip


def _from_sheet_row(record: dict) -> dict:
    """gspread hands back '' for empty cells; restore None and numbers."""
    row = {}
    for col in TRADE_COLUMNS:
        value = record.get(col, "")
        if value == "":
            row[col] = None
        elif col in _NUMERIC:
            row[col] = float(value)
        else:
            row[col] = str(value)
    return row


class LocalStore:
    def __init__(self, path: str | None = None, fresh: bool = False):
        self.path = Path(path or f"{config.LOCAL_DIR}/trades.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if fresh and self.path.exists():
            self.path.unlink()

    def load_trades(self) -> list[dict]:
        if not self.path.exists():
            return []
        with open(self.path) as f:
            return list(json.load(f).values())

    def upsert_trades(self, trades: list[dict]) -> None:
        existing = {t["trade_id"]: t for t in self.load_trades()}
        existing.update({t["trade_id"]: t for t in trades})
        with open(self.path, "w") as f:
            json.dump(existing, f, indent=1)

    def write_summary(self, starting_capital: float) -> None:
        pass  # the summary is computed on demand for local runs


class SheetsStore:
    def __init__(self, spreadsheet=None):
        if spreadsheet is None:
            from src.integrations.google_sheets import get_spreadsheet

            spreadsheet = get_spreadsheet()
        self.spreadsheet = spreadsheet
        self.trades_ws = self._ensure_trades_sheet()
        self._row_of: dict[str, int] = {}

    # -- trades --

    def _ensure_trades_sheet(self):
        from src.integrations.google_sheets import get_or_create_worksheet

        ws = get_or_create_worksheet(
            self.spreadsheet, config.TRADES_SHEET, rows=1000, cols=len(TRADE_COLUMNS)
        )
        if ws.row_values(1) != TRADE_COLUMNS:
            ws.update(values=[TRADE_COLUMNS], range_name="A1")
            self._format_new_sheet(ws)
        return ws

    def _format_new_sheet(self, ws) -> None:
        net_col = TRADE_COLUMNS.index("net_pnl")
        col_range = {"sheetId": ws.id, "startColumnIndex": net_col, "endColumnIndex": net_col + 1, "startRowIndex": 1}
        green, red = {"red": 0.72, "green": 0.88, "blue": 0.80}, {"red": 0.96, "green": 0.78, "blue": 0.76}

        def rule(kind, color):
            return {
                "addConditionalFormatRule": {
                    "index": 0,
                    "rule": {
                        "ranges": [col_range],
                        "booleanRule": {
                            "condition": {"type": kind, "values": [{"userEnteredValue": "0"}]},
                            "format": {"backgroundColor": color},
                        },
                    },
                }
            }

        self.spreadsheet.batch_update(
            {
                "requests": [
                    {
                        "updateSheetProperties": {
                            "properties": {"sheetId": ws.id, "gridProperties": {"frozenRowCount": 1}},
                            "fields": "gridProperties.frozenRowCount",
                        }
                    },
                    {
                        "repeatCell": {
                            "range": {"sheetId": ws.id, "startRowIndex": 0, "endRowIndex": 1},
                            "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                            "fields": "userEnteredFormat.textFormat.bold",
                        }
                    },
                    rule("NUMBER_GREATER", green),
                    rule("NUMBER_LESS", red),
                ]
            }
        )

    def load_trades(self) -> list[dict]:
        records = self.trades_ws.get_all_records(expected_headers=TRADE_COLUMNS)
        return [_from_sheet_row(r) for r in records]

    def upsert_trades(self, trades: list[dict]) -> None:
        if not trades:
            return
        # Row numbers come from the sheet itself each time, so manual row
        # deletions or a second process can't drift us onto the wrong rows.
        ids = self.trades_ws.col_values(1)
        self._row_of = {tid: i + 1 for i, tid in enumerate(ids) if i > 0}

        updates, appends = [], []
        for t in trades:
            values = [t[c] if t[c] is not None else "" for c in TRADE_COLUMNS]
            if t["trade_id"] in self._row_of:
                row = self._row_of[t["trade_id"]]
                updates.append({"range": f"A{row}", "values": [values]})
            else:
                appends.append(values)

        if updates:
            self.trades_ws.batch_update(updates)
        if appends:
            self.trades_ws.append_rows(appends, table_range="A1")

    # -- summary --

    def write_summary(self, starting_capital: float) -> None:
        from src.integrations.google_sheets import get_or_create_worksheet

        trades = self.load_trades()
        s = account_summary(trades, starting_capital)
        rows = [
            ["Paper Trading Summary"],
            [],
            ["Starting capital", s["starting_capital"]],
            ["Equity (realised + open, net of charges)", s["equity"]],
            ["Return %", s["return_pct"]],
            ["Realised net P&L", s["realised_net_pnl"]],
            ["Unrealised net P&L (open positions)", s["unrealised_net_pnl"]],
            ["Gross P&L (closed)", s["gross_pnl"]],
            ["Total charges (closed)", s["total_charges"]],
            [],
            ["Closed trades", s["closed_trades"]],
            ["Open trades", s["open_trades"]],
            ["Skipped signals (no cash / risk too wide)", s["skipped_signals"]],
            ["Win rate % (net P&L > 0)", s["win_rate_pct"]],
            [],
            DAILY_HEADER,
            *daily_table(trades, starting_capital),
        ]
        ws = get_or_create_worksheet(self.spreadsheet, config.SUMMARY_SHEET, rows=200, cols=len(DAILY_HEADER))
        ws.clear()
        ws.update(values=rows, range_name="A1")
