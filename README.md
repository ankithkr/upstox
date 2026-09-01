# upstox

Intraday **top-down ORB** (Opening Range Breakout) strategy tooling for NSE:

- pulls live index / stock quotes and historical candles from Upstox
- pushes heatmapped % change tables to Google Sheets
- backtests the strategy over the cached candle history
- a local web UI ([`ui.py`](ui.py)) for reviewing the universe, the
  backtest results, and a per-day sector → stock heatmap for manual replay

Strategy spec: [`Intraday Top-Down ORB Strategy Documentation.pdf`](Intraday%20Top-Down%20ORB%20Strategy%20Documentation.pdf)

---

## 1. Prerequisites

- **Python 3.13** (3.11+ should work)
- An **Upstox developer app** (API key + secret) — only needed to fetch
  fresh data; the review UI runs fine on the cached data alone
- A **Google Cloud OAuth client** (`creds.json`) — only needed for the
  Google Sheets sync scripts

## 2. Set up the environment

Clone, then create and activate a virtualenv and install the deps.

### Windows (PowerShell)

```powershell
git clone https://github.com/ankithkr/upstox.git
cd upstox
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If PowerShell blocks the activation script, allow it for the current user once:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### Windows (cmd)

```bat
python -m venv venv
venv\Scripts\activate.bat
pip install -r requirements.txt
```

### macOS / Linux

```bash
git clone https://github.com/ankithkr/upstox.git
cd upstox
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 3. Configure

Copy the example env file and fill it in:

```bash
cp .env.example .env
```

| Variable | Needed for | Notes |
| --- | --- | --- |
| `UPSTOX_API_KEY` / `UPSTOX_API_SECRET` | fetching data | from your Upstox app |
| `UPSTOX_REDIRECT_URI` | Upstox login | must match the app config, e.g. `http://localhost:5000/callback` |
| `FLASK_SECRET_KEY` | Upstox login flow | any random string |
| `PORT` | Upstox login flow | default `5000` |
| `UPSTOX_TOKEN_FILE` | all Upstox calls | default `token.json` |
| `GOOGLE_CREDENTIALS_FILE` | Sheets sync | path to the OAuth client `creds.json` |
| `GOOGLE_TOKEN_FILE` | Sheets sync | cached Google token, default `token_google.json` |
| `GOOGLE_SHEET_ID` | Sheets sync | the target spreadsheet's ID |

## 4. Authenticate (only to fetch fresh data)

**Upstox** — the access token expires daily; rerun when it does:

```bash
python upstox_auth.py
```

Then open `http://localhost:5000/`, log in with Upstox, and the token is
saved to `token.json`.

**Google Sheets** (only for the sync scripts) — put your OAuth client
file at `creds.json`, then:

```bash
python authenticate_google.py
```

## 5. Populate the candle cache

Historical candles are cached under `data_cache/candles/` (git-ignored).
Running the backtest fills it:

```bash
python update_backtest_dashboard.py
```

This fetches ~6 months of index and stock candles, runs the backtest, and
writes the summary + trades to Google Sheets. The candle CSVs it leaves
behind are what the review UI reads.

Other data scripts (all require a valid Upstox token, and Sheets access):

| Script | What it does |
| --- | --- |
| `python seed_indices_sheet.py` | seed the `Indices` worksheet with the sector list |
| `python update_indices_sheet.py` | refresh `Indices` with live % change + heatmap |
| `python update_index_stocks_sheet.py` | one worksheet per index with its stocks' live % change |
| `python update_backtest_dashboard.py` | run the backtest, write dashboard + trades |

## 6. Run the review UI

Build the UI's data files from the cached candles (offline — no Upstox
token needed):

```bash
python precompute_ui.py
```

This writes `data_cache/ui_backtest.json` and `data_cache/ui_daily.json`
(takes a few minutes; range auto-resolves to whatever the candle cache
covers). Then start the app:

```bash
python ui.py
```

Open **http://localhost:5001**. Three tabs:

- **Matrix** — each sector index and its constituent stocks
- **Backtest data** — dashboard summary + a filterable table of every trade
- **Date heatmap** — pick a trading day to see the market bias, a
  red→green heatmap of every sector's 09:30 % change, and (on click) a
  drill-down heatmap of that sector's stocks with the simulated ORB trade

The **Rebuild data** button in the UI reruns `precompute_ui.py`.

> The UI never calls Upstox or Google at request time — it only reads the
> JSON built in this step. To widen the date range or refresh it, get a
> new Upstox token, rerun `update_backtest_dashboard.py`, then
> `precompute_ui.py` (or the Rebuild button).

## Project layout

```
src/
  backtest/       ORB simulation, backtest runner, dashboard aggregates
  analysis/       per-day sector/stock snapshots for the UI
  strategy/       market bias, sector selection, momentum filters
  data/           the index and constituent-stock universe
  integrations/   Upstox (auth, quotes, history, instruments) + Google Sheets
  calculations/   % change helper
ui.py             the review web app  (port 5001)
precompute_ui.py  builds the UI's JSON from the candle cache
upstox_auth.py    one-off Upstox OAuth login  (port 5000)
data_cache/       cached candles + generated UI JSON  (git-ignored)
```
