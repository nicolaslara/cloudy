import { describe, expect, it } from "vitest";
import type { CloudPeriod } from "../api/cloud";
import { fillCloudSeries, cloudTooltipHtml } from "./cloudSeries";

function cloudPoint(overrides: Partial<CloudPeriod> = {}): CloudPeriod {
  return {
    period: "2018-07",
    bucket_start: "2018-07-01T00:00:00Z",
    bucket_end: "2018-08-01T00:00:00Z",
    mean_cloud_pct: 42.5,
    min_cloud_pct: 0,
    max_cloud_pct: 100,
    p05_cloud_pct: 0,
    p50_cloud_pct: 50,
    p95_cloud_pct: 100,
    observed_count: 100,
    expected_count: 744,
    missing_count: 644,
    ...overrides,
  };
}

describe("fillCloudSeries", () => {
  it("fills missing periods with null mean, not zero", () => {
    const filled = fillCloudSeries(
      [cloudPoint()],
      "month",
      "2018-07",
      "2018-08",
    );
    expect(filled).toHaveLength(2);
    expect(filled[0]?.mean_cloud_pct).toBe(42.5);
    expect(filled[1]?.mean_cloud_pct).toBeNull();
  });
});

describe("cloudTooltipHtml", () => {
  it("shows missing observations distinctly from clear sky", () => {
    const html = cloudTooltipHtml(
      cloudPoint({ mean_cloud_pct: null, observed_count: 0, missing_count: 744 }),
      "Jul 2018",
    );
    expect(html).toContain("No observations");
    expect(html).toContain("0% of hours");
  });

  it("uses calendar hours in the denominator, not stored rows", () => {
    const html = cloudTooltipHtml(
      cloudPoint(),
      "Jul 2018",
    );
    expect(html).toContain("13% of hours");
  });
});
