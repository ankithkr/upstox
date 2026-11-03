# upstox — paper trading engines

A microservice rebuild of the top-down ORB (Opening Range Breakout) strategy,
built to forward-test it live against real market data and to need minimal
change when it moves from paper trading to real orders.

The previous single-repo backtest/review-UI/paper-trading codebase (the
validated v2 ORB rules, the backtest engine, `paper_trade.py`, the research
scripts) is preserved on the [`legacy/pre-rebuild`](../../tree/legacy/pre-rebuild)
branch. This `main` branch starts the new architecture from scratch; the v2
strategy *rules* are being ported forward into `strategy-engine`, not
re-researched.

## Architecture

```
data-engine --candles--> strategy-engine --signals--> risk-engine --orders--> execution-engine
   (Upstox WS)              (v2 ORB rules)              (sizing/cap)          (Broker: PaperBroker)
                                                                                      |
                                                                                 Supabase (state)
                                                                                      |
                                                              api-gateway  <----------+
                                                            (FastAPI, the only        |
                                                             service the frontend     v
                                                             talks to)            frontend (React)
```

| Service | Job |
|---|---|
| `services/data-engine` | Upstox WebSocket feed, 5-min candle aggregation, market-hours scheduling. Publishes candles to Redis. |
| `services/strategy-engine` | The ported v2 ORB rules: regime gate, sector/stock filters, breakout entry. Publishes signals to Redis. |
| `services/risk-engine` | Position sizing (1% risk, no leverage), daily trade cap, capital checks. Publishes sized order intents to Redis. |
| `services/execution-engine` | Owns the `Broker` interface. Runs `PaperBroker` today; a future `UpstoxLiveBroker` implements the same interface for real orders. Writes trade lifecycle to Supabase. |
| `services/api-gateway` | The only service the frontend talks to. REST/WebSocket over Supabase state. |
| `frontend` | React dashboard (live positions, trade log, equity curve, strategy config). |
| `packages/shared` | Pydantic models (`Candle`, `Signal`, `OrderIntent`, `Trade`, `Position`) and the `Broker` abstract interface, shared by every Python service. |

Each backend service is its own Docker container, talking to the others only
through Redis (live candle/signal stream) and Supabase (persisted business
state — trades, orders, equity, strategy config; raw candle history is kept
in a local/object cache, not Postgres).

## Status

Phases 0-7 are done: every service is real (not a stub), unit-tested, and
`docker compose build` succeeds for all five. The data-engine <-> Upstox
integration (auth, WebSocket connect, protobuf decode) has been verified
against the real Upstox API with live data. The full pipeline
(data-engine -> strategy-engine -> risk-engine -> execution-engine) has
**not yet been run together end-to-end** - that's the next milestone,
blocking on the instrument universe being wired into `INSTRUMENT_KEYS`
(currently just NIFTY 50) and a trading-session window to test in.

| Phase | What it adds |
|---|---|
| 0 | Done: repo restructuring (`legacy/pre-rebuild` branch), this skeleton |
| 1 | Done: Supabase schema (`infra/supabase/migrations`), shared models, `Broker` interface |
| 2 | Done: `data-engine` - Upstox WebSocket client, candle aggregation, market-hours scheduler |
| 3 | Done: `strategy-engine` - the v2 ORB rules ported from `legacy/pre-rebuild` |
| 4 | Done: `risk-engine` - sizing, daily cap, capital checks |
| 5 | Done: `execution-engine` - `PaperBroker`, real cost model |
| 6 | Done: `api-gateway` - REST surface over Supabase, the Upstox OAuth flow |
| 7 | Done: `frontend` - the live dashboard |
| 8 | In progress: deploy. Pivoted from the original Render/managed-worker plan - Render's always-on background workers aren't free, and Oracle Cloud's Always Free tier needs a Visa/Mastercard/Amex (not available here). Current plan: backend runs locally (`docker compose up`, alive during NSE hours) + Supabase (done, real project) + Vercel for the frontend (free, no card). A managed cloud VM is a later upgrade once a compatible card is sorted. |
| 9 | Operational runbook: one full live paper session end-to-end, alerting |
| 10 (later) | Swap in `UpstoxLiveBroker`, add live-money guardrails |

### Upstox login

Upstox (and SEBI) require a fresh login every trading day - there's no way
around this (see the commit history for why: their "extended token" is
business-integration-only and read-only, and unofficial TOTP-replay tools
aren't worth the credential exposure or ToS risk). The dashboard's
**Connect Upstox** button (top right) handles it: it redirects to Upstox's
real login page, and api-gateway's callback exchanges the code and saves
the token to Supabase's `upstox_tokens` table, which `data-engine` reads
from directly - no file to copy between services. `UPSTOX_REDIRECT_URI`
must exactly match what's registered in your Upstox developer app.

## Local development

```bash
cp .env.example .env            # fill in UPSTOX_API_KEY/SECRET, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
docker compose up --build       # redis + all 5 backend services
```

```bash
cd frontend
cp .env.example .env
npm install
npm run dev                     # http://localhost:5173
```

## Project layout

```
packages/shared/     shared Pydantic models + Broker interface
services/
  data-engine/        Upstox WS -> candles -> Redis
  strategy-engine/    v2 ORB rules -> signals -> Redis
  risk-engine/         sizing/caps -> orders -> Redis
  execution-engine/   Broker (PaperBroker) -> Supabase
  api-gateway/         FastAPI, the frontend's only backend contact
frontend/             React dashboard (Vercel)
infra/supabase/migrations/   DB schema
docker-compose.yml    local dev: redis + all backend services
Intraday Top-Down ORB Strategy Documentation.pdf   original strategy spec
```
