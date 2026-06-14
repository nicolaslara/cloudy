import { useMemo } from "react";
import type { Candidate } from "../../api/geocode";
import { useChart } from "../../lib/useChart";
import { useBacktest } from "./api/predictions";
import { BacktestSeriesPanel } from "./BacktestSeriesPanel";
import { ModelLeaderboard } from "./ModelLeaderboard";
import { skillHistogramOption } from "./skillHistogramOption";

/**
 * The "Damped persistence" model page (one tab under the Models section): explains
 * the model in plain words and shows the backtest's verdict as a histogram of
 * per-station skill. The histogram is built on the frontend from the static
 * benchmark the backend supplies (one fetch, cached), so it's "supplied points,
 * drawn here" rather than a baked image. As more models land they each get a
 * sibling page like this.
 */
export function DampedPersistenceView({ selected }: { selected: Candidate | null }) {
  const backtest = useBacktest();
  const damped = backtest.data?.models.damped;
  const option = useMemo(
    () => (damped ? skillHistogramOption(damped.lead1_skills) : null),
    [damped],
  );
  const { containerRef } = useChart(option, "skill-histogram");

  return (
    <div className="normals-view method-view">
      <header className="normals-header">
        <h2>Damped persistence</h2>
        <p className="predictions-intro">
          The model behind the near-term outlook — how it works, and how well it holds up.
        </p>
      </header>

      <section className="method-prose">
        <h3>Damped anomaly persistence</h3>
        <p>
          The seasonal <strong>normal</strong> says what a typical week of the year looks like,
          averaged over all the years we hold. The prediction starts there and adds one idea:
          recent weather has memory. If the last week or two have run cloudier (or clearer) than
          normal, that gap tends to <em>persist</em> for a short while before fading.
        </p>
        <p>
          So the outlook is: <strong>normal + α · (recent gap)</strong>. The factor{" "}
          <strong>α</strong> is how much of the recent gap typically carries forward — measured
          from history as the week-to-week correlation of anomalies — and it shrinks with how far
          ahead we look, so within a few weeks the forecast melts back into the normal. When there's
          no recent gap, α·0 = 0 and the forecast <em>is</em> the normal, which is why it can never
          do worse than the baseline on average.
        </p>
        <p className="method-prose-aside">
          Why weekly, not monthly? Month-to-month anomalies barely persist, so a month-ahead
          forecast is essentially the normal. Weekly anomalies persist enough to beat it — which is
          exactly what the backtest below shows.
        </p>
      </section>

      <section className="normals-panel">
        <h3>Does it beat the normal? (backtest)</h3>
        {backtest.isPending && <p className="normals-source">Loading the backtest…</p>}
        {backtest.error && (
          <p className="normals-source">
            The model hasn't been evaluated yet — run <code>cloudy backtest</code> to generate it.
          </p>
        )}
        {damped && backtest.data && (
          <p className="normals-source">
            Rolling-origin backtest across {backtest.data.n_stations} stations: the weekly outlook
            beats the seasonal normal at{" "}
            <strong>{Math.round(damped.fraction_beating * 100)}%</strong> of them, with a median
            lead-1 skill of <strong>+{damped.median_skill_pct}%</strong> (lead-2 +
            {damped.lead2_median_skill_pct}%). Each bar counts the stations in a skill band; skill is
            the reduction in mean absolute error versus just quoting the normal.
          </p>
        )}
        {/* Always render the canvas host so useChart mounts on it; the option is
            null until the benchmark lands, then the histogram appears. */}
        <div className="chart-area method-histogram">
          <div ref={containerRef} className="chart-canvas" aria-hidden={option === null} />
        </div>
      </section>

      <BacktestSeriesPanel model="damped" selected={selected} />

      <section className="normals-panel">
        <h3>How it ranks</h3>
        <ModelLeaderboard active="damped" />
      </section>
    </div>
  );
}
