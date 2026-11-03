import type { EquitySnapshot, StrategyConfig, Trade } from "./types";

export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function getJson<T>(path: string): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`);
  if (!resp.ok) {
    throw new Error(`${path} failed: ${resp.status} ${resp.statusText}`);
  }
  return resp.json() as Promise<T>;
}

export const api = {
  health: () => getJson<{ status: string }>("/health"),
  trades: (params?: { date?: string; status?: string; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.date) qs.set("date", params.date);
    if (params?.status) qs.set("status", params.status);
    if (params?.limit) qs.set("limit", String(params.limit));
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return getJson<Trade[]>(`/trades${suffix}`);
  },
  positions: () => getJson<Trade[]>("/positions"),
  equityCurve: (limit = 500) => getJson<EquitySnapshot[]>(`/equity-curve?limit=${limit}`),
  strategyConfig: () => getJson<StrategyConfig | null>("/strategy-config"),
};
