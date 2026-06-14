import { describe, expect, it } from "vitest";
import type { CloudNormalPoint, LightningNormalPoint } from "./api/climatology";
import { cloudNormalsOption } from "./cloudNormalsOption";
import { lightningNormalsOption } from "./lightningNormalsOption";

function cloudPoint(overrides: Partial<CloudNormalPoint> = {}): CloudNormalPoint {
  return {
    period: "7",
    mean_cloud_pct: 55,
    p10_cloud_pct: 20,
    p50_cloud_pct: 55,
    p90_cloud_pct: 85,
    clear_pct: 30,
    partial_pct: 25,
    overcast_pct: 45,
    observed_count: 1000,
    year_count: 10,
    ...overrides,
  };
}

function lightningPoint(overrides: Partial<LightningNormalPoint> = {}): LightningNormalPoint {
  return {
    period: "7",
    strike_day_probability: 0.4,
    expected_lightning_days: 12.4,
    mean_count: 320,
    year_count: 10,
    ...overrides,
  };
}

describe("cloudNormalsOption", () => {
  it("draws one mean-cloud-cover bar per slot — the headline answer", () => {
    const option = cloudNormalsOption([cloudPoint({ mean_cloud_pct: 55 })], "month");
    const series = option.series as {
      name: string;
      type: string;
      data: { value: number | null }[];
    }[];

    expect(series).toHaveLength(1);
    expect(series[0]?.type).toBe("bar");
    expect(series[0]?.data.map((d) => d.value)).toEqual([55]);
    // Full 0–100% axis so the bar height reads as an absolute cloud-cover share.
    const yAxis = option.yAxis as { min: number; max: number };
    expect(yAxis).toMatchObject({ min: 0, max: 100 });
  });

  it("shades each bar by its own cloudiness", () => {
    const clear = cloudNormalsOption([cloudPoint({ mean_cloud_pct: 0 })], "month");
    const grey = cloudNormalsOption([cloudPoint({ mean_cloud_pct: 100 })], "month");
    const colorOf = (o: ReturnType<typeof cloudNormalsOption>) =>
      (o.series as { data: { itemStyle: { color: string } }[] }[])[0]?.data[0]?.itemStyle.color;
    // A clear month and an overcast month get different shades.
    expect(colorOf(clear)).not.toEqual(colorOf(grey));
  });

  it("labels month slots by name on the x axis", () => {
    const option = cloudNormalsOption([cloudPoint({ period: "7" })], "month");
    const xAxis = option.xAxis as { data: string[] };
    expect(xAxis.data).toEqual(["Jul"]);
  });
});

describe("lightningNormalsOption", () => {
  it("draws probability bars scaled to percent", () => {
    const option = lightningNormalsOption([lightningPoint()], "month");
    const series = option.series as { type: string; data: (number | null)[] }[];
    expect(series).toHaveLength(1);
    expect(series[0]?.type).toBe("bar");
    expect(series[0]?.data).toEqual([40]); // 0.4 fraction → 40%

    // The axis floors at 0 but fits its top to the data, so small probabilities
    // stay readable rather than being crushed under a fixed 100%.
    const yAxis = option.yAxis as { min: number; max?: number };
    expect(yAxis.min).toBe(0);
    expect(yAxis.max).toBeUndefined();
  });

  it("preserves null probability as a gap", () => {
    const option = lightningNormalsOption(
      [lightningPoint({ strike_day_probability: null })],
      "month",
    );
    const series = option.series as { data: (number | null)[] }[];
    expect(series[0]?.data).toEqual([null]);
  });
});
