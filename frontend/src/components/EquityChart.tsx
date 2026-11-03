import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { EquitySnapshot } from "../types";

export function EquityChart({ snapshots }: { snapshots: EquitySnapshot[] }) {
  if (snapshots.length === 0) {
    return <p className="empty">No equity snapshots yet - nothing has closed a trade.</p>;
  }

  const data = snapshots.map((s) => ({
    ts: new Date(s.ts).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }),
    equity: s.equity,
  }));

  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={data}>
        <XAxis dataKey="ts" tick={{ fontSize: 11 }} minTickGap={24} />
        <YAxis domain={["auto", "auto"]} tick={{ fontSize: 11 }} width={70} />
        <Tooltip />
        <Line type="monotone" dataKey="equity" stroke="#4f8cff" strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
