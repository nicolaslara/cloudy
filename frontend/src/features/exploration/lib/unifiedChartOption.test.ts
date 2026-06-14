import { expect, test } from "vitest";
import type { CloudPeriod } from "../api/cloud";
import type { LightningPeriod } from "../api/lightning";
import { toUnifiedChartOption } from "./unifiedChartOption";

const LIGHTNING: LightningPeriod[] = [
  lightningPoint("2018-06", 0, 0, 0, 0),
  lightningPoint("2018-07", 142, 388, 6, 110.2),
];

const CLOUD: CloudPeriod[] = [
  cloudPoint("2018-06", 55, 700, 720),
  cloudPoint("2018-07", 42.5, 710, 744),
];

function lightningPoint(
  period: string,
  cgCount: number,
  allCount: number,
  lightningDays: number,
  maxAbsPeakKa: number,
): LightningPeriod {
  return {
    period,
    bucket_start: `${period}-01T00:00:00Z`,
    bucket_end: `${period}-02T00:00:00Z`,
    cg_count: cgCount,
    all_count: allCount,
    lightning_days: lightningDays,
    max_abs_peak_ka: maxAbsPeakKa,
    strongest_event_time: null,
  };
}

function cloudPoint(
  period: string,
  meanCloudPct: number,
  observedCount: number,
  expectedCount: number,
): CloudPeriod {
  return {
    period,
    bucket_start: `${period}-01T00:00:00Z`,
    bucket_end: `${period}-02T00:00:00Z`,
    mean_cloud_pct: meanCloudPct,
    min_cloud_pct: 0,
    max_cloud_pct: 100,
    p05_cloud_pct: 0,
    p50_cloud_pct: 50,
    p95_cloud_pct: 100,
    observed_count: observedCount,
    expected_count: expectedCount,
    missing_count: expectedCount - observedCount,
  };
}

test("unified chart shows cloud and strikes without plotting lightning days as a line", () => {
  const option = toUnifiedChartOption(LIGHTNING, CLOUD, "month");
  const yAxes = option.yAxis as { name?: string }[];
  expect(yAxes).toHaveLength(2);
  expect(yAxes.map((axis) => axis.name)).toEqual(["Cloud %", "Strikes"]);

  const series = option.series as { name?: string; type: string; yAxisIndex?: number }[];
  expect(series.map((s) => s.name)).toEqual([
    "Mean cloud cover",
    "All discharges",
    "Cloud-to-ground",
  ]);
  expect(series[0]).toMatchObject({ type: "line", yAxisIndex: 0 });
  expect(series[1]).toMatchObject({ type: "bar", yAxisIndex: 1 });
});

test("unified chart omits cloud series when includeCloud is false", () => {
  const option = toUnifiedChartOption(LIGHTNING, CLOUD, "month", "linear", false);
  const series = option.series as { name?: string }[];
  expect(series.map((s) => s.name)).toEqual(["All discharges", "Cloud-to-ground"]);
});
