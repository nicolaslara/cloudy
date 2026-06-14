import { useMemo } from "react";
import type { Candidate } from "../../api/geocode";
import { useChart } from "../../lib/useChart";
import { backtestErrorOption, backtestSeriesOption } from "./backtestSeriesOption";
import { useBacktestSeries, type ModelId } from "./api/predictions";

/**
 * The backtest as a picture: this model's forecast versus what actually happened,
 * week by week, over the rolling-origin run — with the seasonal normal it must beat
 * drawn alongside. Where the histogram answers "across the country, how often does it
 * win", this answers "here, does it track reality". Located when a place is chosen,
 * Sweden-wide otherwise, so the page always shows the model in action.
 */
export function BacktestSeriesPanel({
  model,
  selected,
}: {
  model: ModelId;
  selected: Candidate | null;
}) {
  // 50 km is the leaderboard's pool radius, so the chart matches the scored skill.
  const series = useBacktestSeries(selected?.lat, selected?.lon, 50, model, 1);
  const points = series.data?.points;
  const option = useMemo(
    () => (points && points.length > 0 ? backtestSeriesOption(points) : null),
    [points],
  );
  const errorOption = useMemo(
    () => (points && points.length > 0 ? backtestErrorOption(points) : null),
    [points],
  );
  const { containerRef } = useChart(option, `backtest-series-${model}`);
  const { containerRef: errorRef } = useChart(errorOption, `backtest-error-${model}`);
  const place = selected ? `near ${selected.label}` : "across Sweden";

  return (
    <section className="normals-panel">
      <h3>Forecast vs actual — {place}</h3>
      {series.isPending && <p className="normals-source">Replaying the backtest…</p>}
      {series.error && (
        <p className="normals-source chart-error">Could not load the backtest. Try again in a moment.</p>
      )}
      {series.data && points && points.length > 0 && (
        <p className="normals-source">
          Each week, the model's one-week-ahead forecast (made from only the data up to that point)
          versus what cloud cover actually turned out to be, with the seasonal normal it's judged
          against. Skill here: <strong>{Math.round(series.data.skill * 100)}%</strong> over{" "}
          {series.data.n_origins} weeks — how much closer the forecast sits to actual than the normal
          does.
        </p>
      )}
      {/* Always mount the canvas host so useChart attaches; the option is null until
          the series lands, then the three lines appear. */}
      <div className="chart-area method-backtest">
        <div ref={containerRef} className="chart-canvas" aria-hidden={option === null} />
      </div>
      {series.data && points && points.length > 0 && (
        <p className="normals-source">
          The gain is hard to read above, so here it is directly: the rolling 52-week mean absolute
          error of the seasonal normal versus the model. Lower is better — the model line sitting
          below the normal is the skill.
        </p>
      )}
      <div className="chart-area method-backtest">
        <div ref={errorRef} className="chart-canvas" aria-hidden={errorOption === null} />
      </div>
    </section>
  );
}
