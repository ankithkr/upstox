-- Initial schema for the paper-trading engines.
-- Business/state data only; raw candle history stays in a local/object cache,
-- not in Postgres.

create table if not exists strategy_configs (
    id          bigint generated always as identity primary key,
    version     text not null,
    params      jsonb not null,
    created_at  timestamptz not null default now()
);

create table if not exists trading_sessions (
    trading_date        date primary key,
    gate_open           boolean not null,
    gate_reason         text,
    equity_start        numeric,
    equity_end          numeric,
    created_at          timestamptz not null default now()
);

create table if not exists signals (
    id              uuid primary key,
    trading_date    date not null references trading_sessions(trading_date),
    symbol          text not null,
    direction       text not null check (direction in ('LONG', 'SHORT')),
    sector          text not null,
    detected_at     timestamptz not null,
    breakout_price  numeric not null,
    stop_price      numeric not null,
    target_price    numeric not null,
    filters_passed  jsonb not null default '[]'::jsonb
);

create table if not exists orders (
    id              uuid primary key,
    signal_id       uuid not null references signals(id),
    symbol          text not null,
    direction       text not null check (direction in ('LONG', 'SHORT')),
    qty             integer not null,
    entry_price     numeric not null,
    stop_price      numeric not null,
    target_price    numeric not null,
    risk_amount     numeric not null,
    created_at      timestamptz not null default now()
);

create table if not exists trades (
    id              uuid primary key,
    order_id        uuid not null references orders(id),
    symbol          text not null,
    direction       text not null check (direction in ('LONG', 'SHORT')),
    status          text not null check (status in ('OPEN', 'CLOSED', 'SKIPPED')),
    qty             integer not null,
    entry_price     numeric,
    entry_time      timestamptz,
    exit_price      numeric,
    exit_time       timestamptz,
    gross_pnl       numeric,
    charges         numeric,
    net_pnl         numeric,
    r_multiple      numeric,
    updated_at      timestamptz not null default now()
);

create table if not exists equity_snapshots (
    id          bigint generated always as identity primary key,
    ts          timestamptz not null,
    equity      numeric not null,
    cash        numeric not null,
    open_risk   numeric not null default 0
);

create index if not exists idx_signals_trading_date on signals(trading_date);
create index if not exists idx_trades_status on trades(status);
create index if not exists idx_equity_snapshots_ts on equity_snapshots(ts);
