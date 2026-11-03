import { api } from "./api";
import { EquityChart } from "./components/EquityChart";
import { PositionsTable } from "./components/PositionsTable";
import { StrategyConfigPanel } from "./components/StrategyConfigPanel";
import { TradeLog } from "./components/TradeLog";
import { usePolling } from "./hooks/usePolling";

export default function App() {
  const health = usePolling(api.health, 30_000);
  const positions = usePolling(api.positions, 15_000);
  const trades = usePolling(() => api.trades({ limit: 100 }), 15_000);
  const equity = usePolling(() => api.equityCurve(500), 15_000);
  const config = usePolling(api.strategyConfig, 60_000);

  const backendOk = health.data?.status === "ok";
  const latestEquity = equity.data?.[equity.data.length - 1]?.equity;

  return (
    <main className="app">
      <header className="header">
        <h1>Paper Trading Dashboard</h1>
        <span className={`backend-badge ${backendOk ? "ok" : "down"}`}>
          api-gateway: {health.error ? "unreachable" : health.data?.status ?? "checking..."}
        </span>
      </header>

      <section className="summary">
        <div className="stat">
          <span className="stat-label">Equity</span>
          <span className="stat-value">{latestEquity != null ? `Rs ${latestEquity.toLocaleString()}` : "-"}</span>
        </div>
        <div className="stat">
          <span className="stat-label">Open positions</span>
          <span className="stat-value">{positions.data?.length ?? "-"}</span>
        </div>
        <div className="stat">
          <span className="stat-label">Trades logged</span>
          <span className="stat-value">{trades.data?.length ?? "-"}</span>
        </div>
      </section>

      <section className="panel">
        <h2>Equity curve</h2>
        {equity.error ? <p className="error">{equity.error}</p> : <EquityChart snapshots={equity.data ?? []} />}
      </section>

      <section className="panel">
        <h2>Open positions</h2>
        {positions.error ? <p className="error">{positions.error}</p> : <PositionsTable positions={positions.data ?? []} />}
      </section>

      <section className="panel">
        <h2>Trade log</h2>
        {trades.error ? <p className="error">{trades.error}</p> : <TradeLog trades={trades.data ?? []} />}
      </section>

      <section className="panel">
        <h2>Strategy config</h2>
        {config.error ? <p className="error">{config.error}</p> : <StrategyConfigPanel config={config.data ?? null} />}
      </section>
    </main>
  );
}
