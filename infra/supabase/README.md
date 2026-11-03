# Supabase

`migrations/0001_init.sql` creates the business-state schema (`strategy_configs`,
`trading_sessions`, `signals`, `orders`, `trades`, `equity_snapshots`) described
in the root README. Raw candle history is **not** stored here.

## One-time setup (once you have a Supabase project)

```bash
npx supabase login
npx supabase link --project-ref <your-project-ref>
npx supabase db push          # applies migrations/0001_init.sql
```

Then put the project's URL and service-role key (Project Settings -> API) into
the root `.env`:

```
SUPABASE_URL=https://<your-project-ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
```

The service-role key is used because `risk-engine`, `execution-engine` and
`api-gateway` are trusted backend services, not browser code — they bypass
row-level security by design. Never ship this key to the frontend.

## Local-only dev (no cloud project yet)

```bash
npx supabase start            # spins up local Postgres + PostgREST + Studio
npx supabase db reset         # applies migrations/ against the local stack
```

This mirrors the hosted project closely enough to develop risk-engine /
execution-engine / api-gateway against before a real Supabase project exists.
Point `.env` at the local stack's printed `API URL` and `service_role` key.
