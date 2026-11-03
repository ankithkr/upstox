import type { Trade } from "../types";

export function PositionsTable({ positions }: { positions: Trade[] }) {
  if (positions.length === 0) {
    return <p className="empty">No open positions.</p>;
  }

  return (
    <table className="table">
      <thead>
        <tr>
          <th>Symbol</th>
          <th>Direction</th>
          <th>Qty</th>
          <th>Entry</th>
          <th>Entry time</th>
        </tr>
      </thead>
      <tbody>
        {positions.map((p) => (
          <tr key={p.id}>
            <td>{p.symbol}</td>
            <td className={p.direction === "LONG" ? "long" : "short"}>{p.direction}</td>
            <td>{p.qty}</td>
            <td>{p.entry_price?.toFixed(2) ?? "-"}</td>
            <td>{p.entry_time ? new Date(p.entry_time).toLocaleTimeString() : "-"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
