import { expect, test } from "vitest";
import type { BarSeriesOption } from "echarts/charts";
import type { DataZoomComponentOption, LegendComponentOption } from "echarts/components";
import { log1pCount, logCountTickLabel, toChartOption, toTimeRangeOption } from "./chartOption";
import type { LightningPeriod } from "../api/lightning";

const SERIES: LightningPeriod[] = [
  lightningPoint("2018-06", 0, 0, 0, 0),
  lightningPoint("2018-07", 142, 388, 6, 110.2),
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

test("plots discharge bars and keeps lightning days out of the main marks", () => {
  const option = toChartOption(SERIES, "month");
  const series = option.series as { name?: string; type: string; yAxisIndex?: number; data?: unknown[] }[];
  expect(series.map((s) => s.name)).toEqual(["All discharges", "Cloud-to-ground"]);
  expect(series[0]).toMatchObject({ type: "bar", yAxisIndex: 0, data: [0, 388] });
  expect(series[1]).toMatchObject({ type: "bar", yAxisIndex: 0, data: [0, 142] });
});

test("legend names all lightning series", () => {
  const legend = toChartOption(SERIES, "month").legend as LegendComponentOption;
  expect(legend.data).toEqual(["All discharges", "Cloud-to-ground"]);
});

test("x axis is the period category axis", () => {
  const option = toChartOption(SERIES, "month");
  const xAxis = option.xAxis as { data: string[] };
  expect(xAxis.data).toEqual(["2018-06", "2018-07"]);
});

test("chart option keeps inside zoom without rendering a second slider", () => {
  const zooms = toChartOption(SERIES, "month").dataZoom as DataZoomComponentOption[];
  expect(zooms.map((zoom) => zoom.type)).toEqual(["inside"]);
  expect(zooms.every((zoom) => zoom.filterMode === "none")).toBe(true);
});

test("time range picker has histogram bars and a data shadow slider", () => {
  const option = toTimeRangeOption(["2018-06", "2018-07"], [0, 388], "month");
  expect((option.series as { type: string }[])[0]?.type).toBe("bar");
  const zooms = option.dataZoom as DataZoomComponentOption[];
  expect(zooms.map((zoom) => zoom.type)).toEqual(["slider", "inside"]);
  const slider = zooms[0] as { showDataShadow?: boolean; borderColor?: string };
  expect(slider.showDataShadow).toBe(true);
  expect(slider.borderColor).toBe("#d3dce6");

  const day = toTimeRangeOption(["2024-01-01", "2024-01-02"], [1, 2], "day");
  const daySlider = (day.dataZoom as DataZoomComponentOption[])[0] as {
    startValue?: string;
    endValue?: string;
  };
  expect(daySlider.startValue).toBeUndefined();
  expect(daySlider.endValue).toBeUndefined();
});

test("tooltip formatter includes lightning days and max kA", () => {
  const option = toChartOption(SERIES, "month");
  const tooltip = option.tooltip as { formatter: (p: { dataIndex: number }[]) => string };
  const html = tooltip.formatter([{ dataIndex: 1 }]);
  expect(html).toContain("Jul 2018");
  expect(html).toContain("All discharges: 388");
  expect(html).toContain("Cloud-to-ground: 142");
  expect(html).toContain("Lightning days: 6");
  expect(html).toContain("110.2 kA");
});

test("log scale transforms discharge counts with log₁₀(1 + n)", () => {
  const option = toChartOption(SERIES, "month", "log");
  const series = option.series as BarSeriesOption[];
  expect(series[0]?.data).toEqual([log1pCount(0), log1pCount(388)]);
  expect(series[1]?.data).toEqual([log1pCount(0), log1pCount(142)]);
  const yAxis = option.yAxis as { minInterval?: number; axisLabel: { formatter: (v: number) => string } };
  expect(yAxis.minInterval).toBeUndefined();
  expect(yAxis.axisLabel.formatter(log1pCount(9))).toBe("9");
  expect(yAxis.axisLabel.formatter(log1pCount(99))).toBe("99");
});

test("logCountTickLabel formats zero and thousands", () => {
  expect(logCountTickLabel(0)).toBe("0");
  expect(logCountTickLabel(log1pCount(1500))).toBe("2k");
});
