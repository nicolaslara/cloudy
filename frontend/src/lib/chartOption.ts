import type { BarSeriesOption } from "echarts/charts";
import type {
  DataZoomComponentOption,
  GridComponentOption,
  LegendComponentOption,
  TooltipComponentOption,
} from "echarts/components";
import type { ComposeOption } from "echarts/core";
import type { LightningPeriod, Resolution } from "../api/lightning";
import { countAxisMax, logCountAxisMax } from "./chartAxis";
import {
  ALL_BOTTOM,
  ALL_TOP,
  AXIS_LABEL,
  CG_BOTTOM,
  CG_TOP,
  SPLIT_LINE,
  barGradient,
  categoryAxisStyle,
} from "./chartStyles";
import { periodLabel, tickLabel } from "./series";

export type ChartOption = ComposeOption<
  | BarSeriesOption
  | GridComponentOption
  | LegendComponentOption
  | TooltipComponentOption
  | DataZoomComponentOption
>;

export type ChartScale = "linear" | "log";

/** log₁₀(1 + n) — keeps zeros visible while compressing spikes. */
export function log1pCount(n: number): number {
  return Math.log10(1 + n);
}

/** Readable tick labels when the axis carries log₁₀(1 + count) values. */
export function logCountTickLabel(logValue: number): string {
  const count = Math.round(10 ** logValue - 1);
  if (count === 0) return "0";
  if (count >= 1000) return `${Math.round(count / 1000)}k`;
  return String(count);
}

/** Last full calendar year — the default daily zoom window. */
export function lastFullYear(): number {
  return new Date().getUTCFullYear() - 1;
}

/** Keep direct chart pan/zoom, but leave the visible slider to TimeRangePicker. */
export function exploreChartDataZoom(): DataZoomComponentOption[] {
  return [{ type: "inside", filterMode: "none" }];
}

function tooltipHtml(point: LightningPeriod, resolution: Resolution): string {
  return [
    `<strong>${periodLabel(point.period, resolution)}</strong>`,
    `All discharges: ${point.all_count}`,
    `Cloud-to-ground: ${point.cg_count}`,
    `Lightning days: ${point.lightning_days}`,
    `Max peak current: ${point.max_abs_peak_ka} kA`,
  ].join("<br/>");
}

function dischargeYValue(count: number, scale: ChartScale): number {
  return scale === "log" ? log1pCount(count) : count;
}

/** Lightning chart: discharge bars. Lightning-day counts stay in the tooltip. */
export function toChartOption(
  series: LightningPeriod[],
  resolution: Resolution,
  scale: ChartScale = "linear",
): ChartOption {
  const useLog = scale === "log";
  const formatter = (params: { dataIndex: number }[]) => {
    const point = series[params[0]?.dataIndex ?? -1];
    return point ? tooltipHtml(point, resolution) : "";
  };

  const dischargeSeries: BarSeriesOption[] = [
    {
      name: "All discharges",
      type: "bar",
      yAxisIndex: 0,
      data: series.map((point) => dischargeYValue(point.all_count, scale)),
      itemStyle: barGradient(ALL_TOP, ALL_BOTTOM),
      barCategoryGap: "25%",
    },
    {
      name: "Cloud-to-ground",
      type: "bar",
      yAxisIndex: 0,
      data: series.map((point) => dischargeYValue(point.cg_count, scale)),
      itemStyle: barGradient(CG_TOP, CG_BOTTOM),
      barGap: "-100%", // overlay on the All bars; later series renders in front
      z: 3,
    },
  ];

  return {
    animation: false,
    grid: { left: 64, right: 40, top: 48, bottom: 44 },
    legend: {
      data: ["All discharges", "Cloud-to-ground"],
      top: 0,
      icon: "roundRect",
    },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "cross" },
      formatter: formatter as TooltipComponentOption["formatter"],
    },
    xAxis: {
      type: "category",
      data: series.map((point) => point.period),
      ...categoryAxisStyle((period) => tickLabel(period, resolution)),
    },
    yAxis: {
      type: "value",
      name: "Strikes",
      min: 0,
      max: useLog ? logCountAxisMax : countAxisMax,
      ...(useLog
        ? {
            axisLabel: {
              color: AXIS_LABEL,
              formatter: (value: number) => logCountTickLabel(value),
            },
          }
        : {
            minInterval: 1,
            axisLabel: { color: AXIS_LABEL },
          }),
      splitLine: { lineStyle: { color: SPLIT_LINE } },
    },
    dataZoom: exploreChartDataZoom(),
    series: dischargeSeries,
  };
}

/** Histogram + dataZoom slider — bars feed the slider data shadow (like the explore charts). */
export function toTimeRangeOption(
  periods: string[],
  counts: number[],
  resolution: Resolution,
): ChartOption {
  return {
    animation: false,
    grid: { left: 64, right: 24, top: 8, bottom: 52 },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    xAxis: {
      type: "category",
      data: periods,
      ...categoryAxisStyle((period) => tickLabel(period, resolution)),
    },
    yAxis: { show: false, scale: true },
    series: [
      {
        type: "bar",
        data: counts,
        itemStyle: {
          borderRadius: [2, 2, 0, 0],
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: ALL_TOP },
              { offset: 1, color: ALL_BOTTOM },
            ],
          },
        },
        barCategoryGap: "25%",
        ...(resolution === "day" ? { barMaxWidth: 3 } : {}),
      },
    ],
    dataZoom: [
      {
        type: "slider",
        showDataShadow: true,
        height: 32,
        bottom: 8,
        borderColor: "#d3dce6",
        fillerColor: "rgba(91, 118, 201, 0.12)",
        dataBackground: {
          lineStyle: { opacity: 0 },
          areaStyle: { color: "rgba(91, 118, 201, 0.25)" },
        },
        selectedDataBackground: {
          lineStyle: { opacity: 0 },
          areaStyle: { color: "rgba(91, 118, 201, 0.45)" },
        },
      },
      { type: "inside" },
    ],
  };
}
