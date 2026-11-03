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

Scaffolding only — every service currently just logs a heartbeat. See the
build phases below for what's next.

| Phase | What it adds |
|---|---|
| 0 | Done: repo restructuring (`legacy/pre-rebuild` branch), this skeleton |
| 1 | Supabase schema (`infra/supabase/migrations`), shared models, `Broker` interface stub |
| 2 | `data-engine`: Upstox WebSocket client, candle aggregation, market-hours scheduler |
| 3 | `strategy-engine`: port the v2 ORB rules from `legacy/pre-rebuild`'s `src/strategy` + `src/backtest` |
| 4 | `risk-engine`: sizing, daily cap, capital checks |
| 5 | `execution-engine`: `PaperBroker`, cost model ported from `legacy/pre-rebuild`'s `src/backtest/costs.py` |
| 6 | `api-gateway`: REST/WS surface for the frontend |
| 7 | `frontend`: the real dashboard |
| 8 | Deploy: Render (background workers for the 4 engines, web service for `api-gateway`), Vercel (frontend), Supabase (DB) |
| 9 | Operational runbook: daily Upstox re-auth, alerting, one full live paper session |
| 10 (later) | Swap in `UpstoxLiveBroker`, add live-money guardrails |

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
