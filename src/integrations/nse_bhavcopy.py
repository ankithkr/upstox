"""Fetch and cache NSE's daily F&O bhavcopy - free, public historical options
and futures data covering every underlying (index + stock) in one file per
trading day, going back years.

NSE switched from a per-year/month archive to the "UDiFF common bhavcopy"
format around mid-2024. This tries the new format first (covers everything
from the switchover onward) and falls back to the old one for older dates.
"""

import csv
import io
import pickle
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import requests

CACHE_DIR = Path("data_cache/fo_bhavcopy")
PARSED_CACHE_DIR = Path("data_cache/fo_bhavcopy_parsed")

# Process-lifetime memo: a backtest run calls fetch_fo_bhavcopy for the same
# day once per symbol it backtests, and re-parsing ~30k rows of CSV each
# time dominates runtime once you're looping over several symbols.
_PARSE_MEMO: dict[date, "list[OptionRow]"] = {}

NEW_URL = "https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{ymd}_F_0000.csv.zip"
OLD_URL = "https://nsearchives.nseindia.com/content/historical/DERIVATIVES/{yyyy}/{mon}/fo{dd}{mon}{yyyy}bhav.csv.zip"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}


@dataclass
class OptionRow:
    symbol: str
    underlying_type: str  # "INDEX" or "STOCK"
    expiry: date
    strike: float
    option_type: str  # "CE" or "PE"
    open: float
    high: float
    low: float
    close: float
    settle: float
    oi: int
    volume: int
    underlying_price: float | None  # None for pre-2024 (old format) dates
    lot_size: int | None  # None for pre-2024 (old format) dates - not carried in that format


def _new_url(d: date) -> str:
    return NEW_URL.format(ymd=d.strftime("%Y%m%d"))


def _old_url(d: date) -> str:
    mon = d.strftime("%b").upper()
    return OLD_URL.format(yyyy=d.year, mon=mon, dd=f"{d.day:02d}")


def _cache_path(d: date) -> Path:
    return CACHE_DIR / f"{d.strftime('%Y%m%d')}.csv"


DOWNLOAD_RETRIES = 3


def _download(url: str) -> bytes | None:
    for attempt in range(1, DOWNLOAD_RETRIES + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
        except requests.exceptions.RequestException:
            if attempt == DOWNLOAD_RETRIES:
                raise
            continue
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.content
    return None


def _extract_csv(zip_bytes: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        return zf.read(zf.namelist()[0]).decode("utf-8")


def fetch_fo_bhavcopy_raw(trade_date: date, force_refresh: bool = False) -> str | None:
    """Raw CSV text for one trading day's F&O bhavcopy, or None if it wasn't a trading day.

    Cached to disk forever - a past day's bhavcopy never changes.
    """
    path = _cache_path(trade_date)
    if not force_refresh and path.exists():
        return path.read_text(encoding="utf-8")

    zip_bytes = _download(_new_url(trade_date))
    if zip_bytes is None:
        zip_bytes = _download(_old_url(trade_date))
    if zip_bytes is None:
        return None

    csv_text = _extract_csv(zip_bytes)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(csv_text, encoding="utf-8")
    return csv_text


def _parse_new_format(csv_text: str) -> list[OptionRow]:
    rows = []
    for r in csv.DictReader(io.StringIO(csv_text)):
        if r["FinInstrmTp"] not in ("STO", "IDO") or r["OptnTp"] not in ("CE", "PE"):
            continue
        rows.append(
            OptionRow(
                symbol=r["TckrSymb"].strip(),
                underlying_type="INDEX" if r["FinInstrmTp"] == "IDO" else "STOCK",
                expiry=date.fromisoformat(r["XpryDt"].strip()),
                strike=float(r["StrkPric"]),
                option_type=r["OptnTp"].strip(),
                open=float(r["OpnPric"]),
                high=float(r["HghPric"]),
                low=float(r["LwPric"]),
                close=float(r["ClsPric"]),
                settle=float(r["SttlmPric"]),
                oi=int(float(r["OpnIntrst"])),
                volume=int(float(r["TtlTradgVol"])),
                underlying_price=float(r["UndrlygPric"]) if r["UndrlygPric"].strip() else None,
                lot_size=int(r["NewBrdLotQty"]) if r["NewBrdLotQty"].strip() else None,
            )
        )
    return rows


def _parse_old_format(csv_text: str) -> list[OptionRow]:
    rows = []
    for r in csv.DictReader(io.StringIO(csv_text)):
        if r["INSTRUMENT"] not in ("OPTSTK", "OPTIDX") or r["OPTION_TYP"] not in ("CE", "PE"):
            continue
        rows.append(
            OptionRow(
                symbol=r["SYMBOL"].strip(),
                underlying_type="INDEX" if r["INSTRUMENT"] == "OPTIDX" else "STOCK",
                expiry=datetime.strptime(r["EXPIRY_DT"].strip(), "%d-%b-%Y").date(),
                strike=float(r["STRIKE_PR"]),
                option_type=r["OPTION_TYP"].strip(),
                open=float(r["OPEN"]),
                high=float(r["HIGH"]),
                low=float(r["LOW"]),
                close=float(r["CLOSE"]),
                settle=float(r["SETTLE_PR"]),
                oi=int(float(r["OPEN_INT"])),
                volume=int(float(r["CONTRACTS"])),
                underlying_price=None,
                lot_size=None,
            )
        )
    return rows


def _parsed_cache_path(d: date) -> Path:
    return PARSED_CACHE_DIR / f"{d.strftime('%Y%m%d')}.pkl"


def fetch_fo_bhavcopy(trade_date: date, force_refresh: bool = False) -> list[OptionRow]:
    """Every index/stock OPTION row (futures excluded) for one trading day, or [] on a holiday.

    Parsing ~30k CSV rows into OptionRow objects is the dominant cost of a
    multi-symbol, multi-year backtest - re-paid every fresh process even
    though the underlying CSV never changes once cached. A pickled copy of
    the parsed rows makes every run after the first one on a given day
    nearly free.
    """
    if not force_refresh and trade_date in _PARSE_MEMO:
        return _PARSE_MEMO[trade_date]

    parsed_path = _parsed_cache_path(trade_date)
    if not force_refresh and parsed_path.exists():
        with open(parsed_path, "rb") as f:
            rows = pickle.load(f)
        _PARSE_MEMO[trade_date] = rows
        return rows

    csv_text = fetch_fo_bhavcopy_raw(trade_date, force_refresh=force_refresh)
    if csv_text is None:
        rows = []
    elif csv_text.lstrip().startswith("TradDt"):
        rows = _parse_new_format(csv_text)
    else:
        rows = _parse_old_format(csv_text)

    _PARSE_MEMO[trade_date] = rows
    PARSED_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(parsed_path, "wb") as f:
        pickle.dump(rows, f, protocol=pickle.HIGHEST_PROTOCOL)
    return rows
