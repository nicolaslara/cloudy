import type { BarSeriesOption } from "echarts/charts";
import type { GridComponentOption, TooltipComponentOption } from "echarts/components";
import type { ComposeOption } from "echarts/core";
import { AXIS_LABEL, SPLIT_LINE, barGradient, categoryAxisStyle } from "../../lib/chartStyles";

export type SkillHistogramOption = ComposeOption<
  BarSeriesOption | GridComponentOption | TooltipComponentOption
>;

// Two-point-wide bins read cleanly for skill that mostly sits in single digits.
const BIN_WIDTH = 2;
// Bars left of zero are losses (slate); right of zero are wins (the cloud blue).
const WIN = ["#7fb0ee", "#aacdf6"] as const;
const LOSS = ["#9aa5b1", "#c2cad3"] as const;

/**
 * Histogram of per-station lead-1 skill vs climatology — the backtest's verdict.
 *
 * Each bar is "this many of the country's stations landed in this skill band";
 * the mass sitting right of 0 is the honest headline ("beats the normal almost
 * everywhere"). Binning is done here from the supplied per-station points so the
 * backend just ships the raw skills and the chart stays a pure transform.
 */
export function skillHistogramOption(skills: number[]): SkillHistogramOption {
  if (skills.length === 0) {
    return { animation: false, xAxis: { type: "category", data: [] }, yAxis: { type: "value" }, series: [] };
  }
  const lo = Math.floor(Math.min(...skills) / BIN_WIDTH) * BIN_WIDTH;
  const hi = Math.ceil(Math.max(...skills) / BIN_WIDTH) * BIN_WIDTH;
  const binCount = Math.max(1, Math.round((hi - lo) / BIN_WIDTH));

  const labels: string[] = [];
  const data: { value: number; itemStyle: BarSeriesOption["itemStyle"] }[] = [];
  for (let i = 0; i < binCount; i++) {
    const start = lo + i * BIN_WIDTH;
    const count = skills.filter((s) => s >= start && s < start + BIN_WIDTH).length;
    labels.push(`${start}%`);
    // A bin counts as a "win" band once its whole range is at or above zero.
    const [top, bottom] = start >= 0 ? WIN : LOSS;
    data.push({ value: count, itemStyle: barGradient(top, bottom) });
  }

  return {
    animation: false,
    grid: { left: 40, right: 16, top: 16, bottom: 40 },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: ((params: { name: string; value: number }[]) => {
        const p = params[0];
        return p ? `${p.value} station${p.value === 1 ? "" : "s"} at ${p.name} skill` : "";
      }) as TooltipComponentOption["formatter"],
    },
    xAxis: {
      type: "category",
      data: labels,
      name: "lead-1 skill vs climatology",
      nameLocation: "middle",
      nameGap: 26,
      nameTextStyle: { color: AXIS_LABEL },
      ...categoryAxisStyle((value) => value),
    },
    yAxis: {
      type: "value",
      name: "stations",
      axisLabel: { color: AXIS_LABEL },
      splitLine: { lineStyle: { color: SPLIT_LINE } },
    },
    series: [{ type: "bar", data, barWidth: "85%" }],
  };
}
