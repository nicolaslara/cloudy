import { useHealth } from "../api/health";

const COPY = {
  ok: "Backend and database are up.",
  degraded: "Backend is up, but the database is unreachable.",
  unreachable: "Backend is unreachable.",
} as const;

export function HealthCard() {
  const { data, error, isPending } = useHealth();

  if (isPending) {
    return <section className="card">Checking backend…</section>;
  }

  const state = error ? "unreachable" : data.status === "ok" ? "ok" : "degraded";

  return (
    <section className={`card card-${state}`}>
      <h2>Backend health</h2>
      <p>
        <strong data-testid="health-state">{state}</strong> — {COPY[state]}
      </p>
    </section>
  );
}
