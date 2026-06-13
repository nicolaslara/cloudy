import type { CloudPeriod } from "../api/cloud";
import type { Resolution } from "../api/lightning";
import { periodKeys } from "./series";

/** Fill API gaps so the chart axis is continuous; missing periods stay null (not 0%). */
export function fillCloudSeries(
  series: CloudPeriod[],
  resolution: Resolution,
  from: string,
  to: string,
): CloudPeriod[] {
  if (resolution === "raw") return series;
  const byPeriod = new Map(series.map((point) => [point.period, point]));
  return periodKeys(resolution, from, to).map(
    (period) =>
      byPeriod.get(period) ?? {
        period,
        bucket_start: `${period.slice(0, 10)}T00:00:00Z`,
        bucket_end: `${period.slice(0, 10)}T00:00:00Z`,
        mean_cloud_pct: null,
        min_cloud_pct: null,
        max_cloud_pct: null,
        p05_cloud_pct: null,
        p50_cloud_pct: null,
        p95_cloud_pct: null,
        observed_count: 0,
        expected_count: 0,
        missing_count: 0,
      },
  );
}

export function cloudTooltipHtml(point: CloudPeriod, label: string): string {
  const mean =
    point.mean_cloud_pct === null ? "No observations" : `${point.mean_cloud_pct}%`;
  const coverage =
    point.expected_count > 0
      ? `${Math.round((point.observed_count / point.expected_count) * 100)}% of hours`
      : "No expected hours";
  return [`<strong>${label}</strong>`, `Mean cloud cover: ${mean}`, `Coverage: ${coverage}`].join(
    "<br/>",
  );
}
