"""Local backtest review UI.

A small Flask app for reading the ORB strategy's rules, eyeballing its
universe and backtest results, and replaying any day by hand through a
sector -> stock heatmap that shows which filter accepted or rejected each name. All data is served from the JSON files written by
precompute_ui.py (which in turn read the local Upstox candle cache);
nothing here calls Upstox or Google at request time.

    python ui.py    then open http://localhost:5001
"""

import json
import subprocess
import sys
from pathlib import Path

from flask import Flask, jsonify, render_template

from src.data.indices import SECTOR_INDEX_INSTRUMENT_KEYS
from src.data.stocks import INDEX_CONSTITUENTS
from src.data.universe import LIQUID_UNIVERSE, V2_SECTORS
from src.strategy.params import DEFAULT_PARAMS, describe

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data_cache"
BACKTEST_JSON = DATA_DIR / "ui_backtest.json"
DAILY_JSON = DATA_DIR / "ui_daily.json"

app = Flask(__name__, template_folder="webui/templates")


_CACHE: dict[Path, tuple[float, dict]] = {}


def _load(path: Path):
    """Parse a precomputed JSON, re-reading only when the file changes (ui_daily.json is ~20 MB)."""
    if not path.exists():
        return None
    mtime = path.stat().st_mtime
    hit = _CACHE.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    with open(path) as f:
        data = json.load(f)
    _CACHE[path] = (mtime, data)
    return data


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/strategy")
def api_strategy():
    return jsonify({"params": DEFAULT_PARAMS.as_dict(), "rules": describe(DEFAULT_PARAMS)})


@app.route("/api/matrix")
def api_matrix():
    universe = set(LIQUID_UNIVERSE)
    rows = []
    for name in V2_SECTORS:
        constituents = INDEX_CONSTITUENTS.get(name, [])
        rows.append(
            {
                "sector": name,
                "instrument_key": SECTOR_INDEX_INSTRUMENT_KEYS.get(name),
                "stocks": [s for s in constituents if s in universe],
                "excluded": [s for s in constituents if s not in universe],
            }
        )
    return jsonify({"sectors": rows, "universe_size": len(universe)})


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
            "gate_ok": d["gate_ok"],
            "vix": d["vix"],
            "trades_taken": d["trades_taken"],
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
    # 0.0.0.0 so the port mapping works when this runs inside Docker;
    # still reachable at localhost:5001 when run directly.
    app.run(host="0.0.0.0", port=5001, debug=True)
