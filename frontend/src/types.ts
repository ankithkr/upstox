// Mirrors packages/shared/shared/models.py's Trade and the api-gateway
// response schemas (services/api-gateway/app/schemas.py). Keep these two
// in sync by hand - there's no shared codegen between Python and
// TypeScript here yet.

export type Direction = "LONG" | "SHORT";
export type TradeStatus = "OPEN" | "CLOSED" | "SKIPPED";

export interface Trade {
  id: string;
  order_id: string;
  symbol: string;
  direction: Direction;
  status: TradeStatus;
  qty: number;
  entry_price: number | null;
  entry_time: string | null;
  exit_price: number | null;
  exit_time: string | null;
  gross_pnl: number | null;
  charges: number | null;
  net_pnl: number | null;
  r_multiple: number | null;
}

export interface EquitySnapshot {
  ts: string;
  equity: number;
  cash: number;
  open_risk: number;
}

export interface StrategyConfig {
  version: string;
  params: Record<string, number | string | boolean | null>;
  created_at: string;
}
