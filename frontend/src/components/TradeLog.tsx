import type { Trade } from "../types";

export function TradeLog({ trades }: { trades: Trade[] }) {
  if (trades.length === 0) {
    return <p className="empty">No trades yet.</p>;
  }

  return (
    <table className="table">
      <thead>
        <tr>
          <th>Symbol</th>
          <th>Direction</th>
          <th>Status</th>
          <th>Qty</th>
          <th>Entry</th>
          <th>Exit</th>
          <th>Net P&amp;L</th>
          <th>R</th>
        </tr>
      </thead>
      <tbody>
        {trades.map((t) => (
          <tr key={t.id}>
            <td>{t.symbol}</td>
            <td className={t.direction === "LONG" ? "long" : "short"}>{t.direction}</td>
            <td>
              <span className={`status status-${t.status.toLowerCase()}`}>{t.status}</span>
            </td>
            <td>{t.qty}</td>
            <td>{t.entry_price?.toFixed(2) ?? "-"}</td>
            <td>{t.exit_price?.toFixed(2) ?? "-"}</td>
            <td className={(t.net_pnl ?? 0) >= 0 ? "pnl-positive" : "pnl-negative"}>
              {t.net_pnl != null ? t.net_pnl.toFixed(2) : "-"}
            </td>
            <td>{t.r_multiple != null ? t.r_multiple.toFixed(2) : "-"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
