import type { CloudCurrentMonth, LightningCurrentMonth } from "./api/climatology";
import { monthName } from "./periodLabel";

// The callout is the live counterpart to the long-run normal: it answers "is this
// month running typical?" by putting the blended expectation next to the plain
// all-years baseline. We phrase the gap in plain language (cloudier/clearer,
// more/fewer storm days) because a signed delta is the one number a casual
// reader actually wants from a normals page.

function deltaPhrase(expected: number, baseline: number, more: string, less: string): string {
  const diff = Math.round((expected - baseline) * 10) / 10;
  if (Math.abs(diff) < 0.5) return "running about typical for this time of year";
  const dir = diff > 0 ? more : less;
  return `running ${dir} than typical`;
}

export function CloudCurrentMonthCallout({ data }: { data: CloudCurrentMonth }) {
  const { expected_pct, baseline_pct } = data;
  // With no observations yet (start of a month, or a thin station) there's nothing
  // honest to compare, so we stay silent rather than invent an expectation.
  if (expected_pct == null || baseline_pct == null) return null;

  return (
    <aside className="normals-callout" aria-label="Current month vs normal">
      <h3>Current month vs normal</h3>
      <p>
        {monthName(data.month)} is on track for{" "}
        <strong>{Math.round(expected_pct)}% cloud cover</strong>, versus a typical{" "}
        {Math.round(baseline_pct)}% — {deltaPhrase(expected_pct, baseline_pct, "cloudier", "clearer")}.
      </p>
    </aside>
  );
}

export function LightningCurrentMonthCallout({ data }: { data: LightningCurrentMonth }) {
  const { expected_lightning_days, baseline_days } = data;
  if (expected_lightning_days == null || baseline_days == null) return null;

  const days = (v: number) => `${Math.round(v * 10) / 10} day${Math.round(v) === 1 ? "" : "s"}`;
  return (
    <aside className="normals-callout" aria-label="Current month vs normal">
      <h3>Current month vs normal</h3>
      <p>
        {monthName(data.month)} is on track for{" "}
        <strong>{days(expected_lightning_days)} of lightning</strong>, versus a typical{" "}
        {days(baseline_days)} —{" "}
        {deltaPhrase(expected_lightning_days, baseline_days, "more active", "quieter")}.
      </p>
    </aside>
  );
}
