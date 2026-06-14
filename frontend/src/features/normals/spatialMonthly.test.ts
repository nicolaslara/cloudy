import { describe, expect, it } from "vitest";
import type { SpatialNormalPoint } from "./api/climatology";
import { spatialMonthlyMeans } from "./spatialMonthly";

function spatialPoint(overrides: Partial<SpatialNormalPoint> = {}): SpatialNormalPoint {
  return { week: 1, estimated_cloud_pct: 70, ...overrides };
}

describe("spatialMonthlyMeans", () => {
  it("folds the weekly curve into twelve monthly means", () => {
    // Week 1 (early Jan) and week 27 (early Jul) land in different months.
    const means = spatialMonthlyMeans([
      spatialPoint({ week: 1, estimated_cloud_pct: 80 }),
      spatialPoint({ week: 27, estimated_cloud_pct: 40 }),
    ]);
    expect(means.get("1")).toBe(80);
    expect(means.get("7")).toBe(40);
  });

  it("averages weeks that fall in the same month", () => {
    const means = spatialMonthlyMeans([
      spatialPoint({ week: 1, estimated_cloud_pct: 60 }),
      spatialPoint({ week: 2, estimated_cloud_pct: 80 }),
    ]);
    expect(means.get("1")).toBe(70);
  });

  it("returns null for a month with no usable week", () => {
    const means = spatialMonthlyMeans([spatialPoint({ week: 1, estimated_cloud_pct: 50 })]);
    expect(means.get("6")).toBeNull();
  });

  it("drops null estimates from their month's average", () => {
    const means = spatialMonthlyMeans([
      spatialPoint({ week: 1, estimated_cloud_pct: null }),
      spatialPoint({ week: 2, estimated_cloud_pct: 90 }),
    ]);
    expect(means.get("1")).toBe(90);
  });
});
