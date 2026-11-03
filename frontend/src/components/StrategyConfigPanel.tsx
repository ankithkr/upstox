import type { StrategyConfig } from "../types";

export function StrategyConfigPanel({ config }: { config: StrategyConfig | null }) {
  if (!config) {
    return <p className="empty">No strategy config published yet - strategy-engine publishes one on startup.</p>;
  }

  const entries = Object.entries(config.params);

  return (
    <div>
      <p className="config-meta">
        {config.version} - published {new Date(config.created_at).toLocaleString()}
      </p>
      <table className="table">
        <tbody>
          {entries.map(([key, value]) => (
            <tr key={key}>
              <td className="config-key">{key}</td>
              <td>{String(value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
