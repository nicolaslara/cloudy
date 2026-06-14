import { useBacktest, type BacktestArtifact, type ModelId } from "./api/predictions";

// Display names for the leaderboard rows, keyed by the backend's model ids. Adding
// a model means a field in BacktestModels (backend) and an entry here.
export const MODEL_LABELS: Record<ModelId, string> = {
  damped: "Damped persistence",
};

// Stable row order — the order models read down the table, independent of object
// key order in the JSON.
const MODEL_ORDER: ModelId[] = ["damped"];

// Signed percent: a leading "+" only for non-negative values, since a negative
// already carries its "−". Shared so a losing model reads "-4.4%", never "+-4.4%".
export function signedPct(v: number): string {
  return `${v >= 0 ? "+" : ""}${v}%`;
}

/**
 * The leaderboard: every weekly model scored on the same stations and harness, so
 * a model page can show "here's how I stack up" rather than a number in isolation.
 * The current page's row is highlighted. Skill is the median per-station reduction
 * in mean absolute error versus quoting the seasonal normal; higher is better.
 */
export function ModelLeaderboard({ active }: { active: ModelId }) {
  const backtest = useBacktest();
  if (!backtest.data) return null;
  const { models, n_stations } = backtest.data as BacktestArtifact;

  return (
    <table className="model-leaderboard">
      <caption>Median skill vs the seasonal normal, across {n_stations} stations</caption>
      <thead>
        <tr>
          <th scope="col">Model</th>
          <th scope="col">Skill @1wk</th>
          <th scope="col">Skill @2wk</th>
          <th scope="col">Stations beating</th>
        </tr>
      </thead>
      <tbody>
        {MODEL_ORDER.map((id) => {
          const m = models[id];
          return (
            <tr key={id} className={id === active ? "active" : undefined}>
              <th scope="row">{MODEL_LABELS[id]}</th>
              <td>{signedPct(m.median_skill_pct)}</td>
              <td>{signedPct(m.lead2_median_skill_pct)}</td>
              <td>{Math.round(m.fraction_beating * 100)}%</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
