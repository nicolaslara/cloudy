import { describe, expect, it } from "vitest";
import type { CloudPeriod } from "../api/cloud";
import { toCloudChartOption } from "./cloudChartOption";

function cloudPoint(overrides: Partial<CloudPeriod> = {}): CloudPeriod {
  return {
    period: "2018-07",
    bucket_start: "2018-07-01T00:00:00Z",
    bucket_end: "2018-08-01T00:00:00Z",
    mean_cloud_pct: 50,
    min_cloud_pct: 0,
    max_cloud_pct: 100,
    p05_cloud_pct: 0,
    p50_cloud_pct: 50,
    p95_cloud_pct: 100,
    observed_count: 12,
    expected_count: 24,
    missing_count: 12,
    ...overrides,
  };
}

describe("toCloudChartOption", () => {
  it("extends the y axis slightly above 100% for top padding and preserves null gaps", () => {
    const option = toCloudChartOption(
      [
        cloudPoint(),
        cloudPoint({
          period: "2018-08",
          bucket_start: "2018-08-01T00:00:00Z",
          bucket_end: "2018-09-01T00:00:00Z",
          mean_cloud_pct: null,
          observed_count: 0,
          expected_count: 0,
          missing_count: 0,
        }),
      ],
      "month",
    );
    expect(option.yAxis).toMatchObject({ min: 0, max: 105 });
    const series = option.series as { data: (number | null)[] }[];
    expect(series[0]?.data).toEqual([50, null]);
  });

  it("anchors the area to the frame edges instead of insetting half a bucket", () => {
    const option = toCloudChartOption([cloudPoint()], "month");
    expect(option.xAxis).toMatchObject({ boundaryGap: false });
  });
});
