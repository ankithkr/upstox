# upstox

Intraday **top-down ORB** (Opening Range Breakout) strategy tooling for NSE:

- pulls live index / stock quotes and historical candles from Upstox
- pushes heatmapped % change tables to Google Sheets
- backtests the strategy over the cached candle history
- a local web UI ([`ui.py`](ui.py)) for reviewing the universe, the
  backtest results, and a per-day sector → stock heatmap for manual replay

Original strategy spec: [`Intraday Top-Down ORB Strategy Documentation.pdf`](Intraday%20Top-Down%20ORB%20Strategy%20Documentation.pdf).
The backtest and review UI now run the **v2 strategy** below, which was
tuned and validated on 2023-2026 data (the PDF rules lost money after
costs). The paper-trading engine (section 7) still implements the PDF rules
and has not been moved to v2 yet.

## The v2 strategy in brief

A 30-minute opening-range breakout, taken only in a calm, trending market
and only on volume. All numbers live in
[`src/strategy/params.py`](src/strategy/params.py) and are shown in the UI's
**Strategy** tab.

1. **Regime gate** - NIFTY's 09:30 move (> +/-0.3%) picks the side. Skip the
   day unless the previous-close India VIX is < 14 *and* NIFTY's previous
   close is on the right side of its 20-day average (above for longs).
2. **Sectors** - the 3 strongest (longs) / weakest (shorts) liquid sector indices at 09:30.
3. **Stocks** - from the 120 most-liquid names: moved 0.8%-2.5% with the trade at
   09:30, opening volume >= 1x its 20-day norm.
4. **Entry** - a 5-minute close beyond the 09:15-09:45 range, entry stop at that
   candle's high/low; the breakout candle's volume must be >= 1.5x normal.
5. **Stop / exit** - stop beyond the breakout candle but never closer than 0.4x the
   14-day ATR; target 3R; stop to entry at 1.5R; forced exit 15:15.
6. **Limit** - at most 3 trades a day. Results are reported in R after costs
   (Rs 12.5/order brokerage, STT, exchange, GST, stamp, 0.03% slippage).

Backtest over 2023-01 -> 2026-08 (908 days): 199 trades on 89 days, about
+0.21R per trade after costs, positive in every year. Treat that as a
hypothesis, not a result: the thresholds were chosen on this same history, the
stock universe is picked by *current* liquidity, and the edge shrinks to ~+0.1R
if real costs are 0.2% instead of 0.124%. The research that led here is in
`research2.py` and `exp1.py`-`exp8.py` (outputs in `exp*_out.txt`).

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
The backtest and UI read **only** this cache - they never call Upstox.

```bash
python fetch_history.py     # one-off multi-year backfill (~1.5-2 h, throttled, resumable)
python refresh_cache.py     # afterwards: top up everything since the last cached day (minutes)
```

`fetch_history.py` pulls 5-minute candles for the 120-stock universe,
15-minute candles for NIFTY 50 and the 16 sector indices, and daily candles
(including India VIX) back to Jan 2023. `refresh_cache.py` only fetches what
is missing, up to yesterday. Both need a working Upstox token (see section 4).

Other data scripts (all require a valid Upstox token, and Sheets access):

| Script | What it does |
| --- | --- |
| `python seed_indices_sheet.py` | seed the `Indices` worksheet with the sector list |
| `python update_indices_sheet.py` | refresh `Indices` with live % change + heatmap |
| `python update_index_stocks_sheet.py` | one worksheet per index with its stocks' live % change |
| `python update_backtest_dashboard.py` | run the v2 backtest from the cache, write dashboard + trades to Sheets |

## 6. Run the review UI

Build the UI's data files from the cached candles (offline — no Upstox
token needed):

```bash
python precompute_ui.py
```

This writes `data_cache/ui_backtest.json` and `data_cache/ui_daily.json`
(about a minute; it covers every day in the candle cache). Then start the app:

```bash
python ui.py
```

Open **http://localhost:5001**. Four tabs:

- **Strategy** — the six rules and every parameter, generated from the code
- **Backtest data** — net R per trade, profit factor, drawdown, a cumulative-R
  chart, breakdowns by year/month/sector/direction, and a filterable table of every trade
- **Date heatmap** — pick a trading day to see the regime gate (NIFTY move,
  20-day trend, VIX, breadth, open/closed and why), a red→green heatmap of every
  sector's 09:30 % change, and (on click) its stocks; click a stock to see
  which filters it passed and its simulated trade, before and after costs
- **Universe** — each sector index and its tradable stocks

The **Rebuild data** button in the UI reruns `precompute_ui.py`.

> The UI never calls Upstox or Google at request time — it only reads the
> JSON built in this step. To widen the date range or refresh it, get a
> new Upstox token, rerun `update_backtest_dashboard.py`, then
> `precompute_ui.py` (or the Rebuild button).

### Run it with Docker instead

If the native setup above gives you trouble (e.g. Python version/pip
issues on macOS), run the review UI in Docker instead — you still need
`data_cache/` populated first (step 5, done on any machine), but skip
the venv/Python setup entirely.

```bash
docker compose up --build
```

Open **http://localhost:5001**. This mounts your local `data_cache/`
into the container (so it reads/writes the same candles and UI JSON as
a native run) and `instruments_nse.json` read-only (only needed for the
in-app **Rebuild data** button — comment that line out of
`docker-compose.yml` if you don't have the file).

Without Compose:

```bash
docker build -t upstox-review-ui .
docker run --rm -p 5001:5001 \
  -v "$(pwd)/data_cache:/app/data_cache" \
  -v "$(pwd)/instruments_nse.json:/app/instruments_nse.json:ro" \
  upstox-review-ui
```

## 7. Paper trading (forward test)

[`paper_trade.py`](paper_trade.py) runs the strategy live against a
simulated Rs 1,00,000 account and records every trade in Google Sheets.
No real orders are ever placed.

```bash
python upstox_auth.py            # fresh Upstox token (expires daily)
python authenticate_google.py    # only if the Google token has lapsed
python paper_trade.py live       # start before 09:30 IST, leave running to ~15:20
```

It ticks after each 5-minute candle closes: at 09:30 it applies the
top-down filter (NIFTY bias, sector, stock), then walks each qualifying
stock through breakout, entry, stop-loss, 1:2 target, breakeven at 1:1
and the 15:15 force exit. Safe to stop and restart - every tick
recomputes the day from the candles and upserts trades by id.

| Sheet | Contents |
| --- | --- |
| `Paper Trades` | one row per trade: entry/SL/target, qty, status (`OPEN` / `CLOSED` / `SKIPPED`), outcome, gross P&L, charges, net P&L, R multiple |
| `Paper Summary` | equity, return, win rate, charges, and a per-day P&L / equity table |

Rules (all editable in [`src/paper/config.py`](src/paper/config.py)):

- **Capital** Rs 1,00,000 (`PAPER_CAPITAL` env var overrides). Risk per trade is
  1% of start-of-day equity: `qty = risk / (entry - SL)`.
- **No leverage.** A position's value must fit in free cash, so qty is
  capped by cash; a signal that finds no cash is logged as `SKIPPED`, not lost.
- **Charges** (brokerage, STT, exchange, GST, stamp) are deducted; the rates in
  [`src/paper/charges.py`](src/paper/charges.py) are estimates - verify them.
- One position per stock per day; no new entries in the last candle.
- Orders are modelled as resting stop-entry / SL / target orders on closed
  5-minute candles. A candle that gaps past an order fills at its open.

Other commands:

```bash
python paper_trade.py status            # account summary from the store
python paper_trade.py replay -v         # replay all cached days offline (validation only;
                                        # writes data_cache/paper/replay_trades.json, never Sheets)
python paper_trade.py live --store local   # dry run to a local JSON file instead of Sheets
python -m unittest discover -s tests    # engine tests
```

## Project layout

```
src/
  backtest/       ORB simulation, per-day snapshots (the v2 funnel), runner, costs, dashboard aggregates
  analysis/       thin wrapper exposing the snapshots to the UI
  strategy/       v2 parameters + rule text; (legacy) market bias, sector selection, momentum filters
  paper/          paper-trading engine, sizing, charges, Sheets/local stores
  data/           the index and constituent-stock universe
  integrations/   Upstox (auth, quotes, history, instruments) + Google Sheets
  calculations/   % change helper
ui.py             the review web app  (port 5001)
paper_trade.py    the paper-trading (forward test) runner
tests/            paper engine + v2 strategy tests
precompute_ui.py  builds the UI's JSON from the candle cache
fetch_history.py, refresh_cache.py   multi-year backfill / incremental top-up of the cache
research2.py, exp*.py   the research harness and experiments behind the v2 rules
upstox_auth.py    one-off Upstox OAuth login  (port 5000)
data_cache/       cached candles + generated UI JSON  (git-ignored)
Dockerfile, docker-compose.yml   containerized review UI (see above)
```
