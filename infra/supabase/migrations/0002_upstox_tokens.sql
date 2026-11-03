-- Current Upstox access token, written by api-gateway's OAuth callback
-- (/auth/upstox/login -> Upstox -> /auth/upstox/callback), read by
-- data-engine instead of a locally mounted token.json. One row per
-- login; readers take the most recent by obtained_at.
--
-- The token itself is still short-lived (expires daily, per Upstox/SEBI
-- rules) - this table only changes *where* it's stored, not that it
-- still needs a fresh login each trading day.

create table if not exists upstox_tokens (
    id           bigint generated always as identity primary key,
    access_token text not null,
    obtained_at  timestamptz not null default now()
);

create index if not exists idx_upstox_tokens_obtained_at on upstox_tokens(obtained_at desc);
