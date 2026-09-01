"""Local backtest review UI.

A small Flask app for eyeballing the ORB strategy's universe, the
backtest results, and a per-day sector -> stock heatmap so setups can
be replayed by hand. All data is served from the JSON files written by
precompute_ui.py (which in turn read the local Upstox candle cache);
nothing here calls Upstox or Google at request time.

    python ui.py    then open http://localhost:5001
"""

import json
import subprocess
import sys
from pathlib import Path

from flask import Flask, jsonify, render_template

from src.data.indices import SECTOR_INDEX_INSTRUMENT_KEYS, SECTOR_INDICES
from src.data.stocks import INDEX_CONSTITUENTS

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data_cache"
BACKTEST_JSON = DATA_DIR / "ui_backtest.json"
DAILY_JSON = DATA_DIR / "ui_daily.json"

app = Flask(__name__, template_folder="webui/templates")


def _load(path: Path):
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/matrix")
def api_matrix():
    rows = []
    for name in SECTOR_INDICES:
        rows.append(
            {
                "sector": name,
                "instrument_key": SECTOR_INDEX_INSTRUMENT_KEYS.get(name),
                "stocks": INDEX_CONSTITUENTS.get(name, []),
            }
        )
    return jsonify({"sectors": rows})


@app.route("/api/backtest")
def api_backtest():
    data = _load(BACKTEST_JSON)
    if data is None:
        return jsonify({"error": "not_built"}), 404
    return jsonify(data)


@app.route("/api/daily")
def api_daily():
    data = _load(DAILY_JSON)
    if data is None:
        return jsonify({"error": "not_built"}), 404
    summary = [
        {
            "date": d["date"],
            "nifty_change": d["nifty_change"],
            "market_bias": d["market_bias"],
            "direction": d["direction"],
            "selected_sectors": [s["name"] for s in d["sectors"] if s["selected"]],
        }
        for d in sorted(data["days"].values(), key=lambda x: x["date"])
    ]
    return jsonify({"days": summary, "missing_symbols": data.get("missing_symbols", []),
                    "start": data.get("start"), "end": data.get("end")})


@app.route("/api/daily/<day>")
def api_daily_detail(day):
    data = _load(DAILY_JSON)
    if data is None:
        return jsonify({"error": "not_built"}), 404
    detail = data["days"].get(day)
    if detail is None:
        return jsonify({"error": "no_such_day"}), 404
    return jsonify(detail)


@app.route("/api/rebuild", methods=["POST"])
def api_rebuild():
    proc = subprocess.run(
        [sys.executable, str(BASE_DIR / "precompute_ui.py")],
        capture_output=True, text=True, cwd=BASE_DIR,
    )
    ok = proc.returncode == 0
    return jsonify({"ok": ok, "stdout": proc.stdout[-4000:], "stderr": proc.stderr[-4000:]}), (200 if ok else 500)


if __name__ == "__main__":
    app.run(port=5001, debug=True)
