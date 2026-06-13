import type { BarSeriesOption, LineSeriesOption } from "echarts/charts";
import type {
  DataZoomComponentOption,
  GridComponentOption,
  LegendComponentOption,
  TooltipComponentOption,
} from "echarts/components";
import type { ComposeOption } from "echarts/core";
import type { CloudPeriod } from "../api/cloud";
import type { LightningPeriod, Resolution } from "../api/lightning";
import {
  exploreChartDataZoom,
  log1pCount,
  logCountTickLabel,
  type ChartScale,
} from "./chartOption";
import { CLOUD_PERCENT_AXIS_MAX, countAxisMax, logCountAxisMax } from "./chartAxis";
import {
  ALL_BOTTOM,
  ALL_TOP,
  AXIS_LABEL,
  CG_BOTTOM,
  CG_TOP,
  CLOUD_AREA_OVERLAY,
  CLOUD_LINE,
  SPLIT_LINE,
  barGradient,
  categoryAxisStyle,
} from "./chartStyles";
import { cloudTooltipHtml } from "./cloudSeries";
import { periodLabel, tickLabel } from "./series";

export type UnifiedChartOption = ComposeOption<
  | BarSeriesOption
  | LineSeriesOption
  | GridComponentOption
  | LegendComponentOption
  | TooltipComponentOption
  | DataZoomComponentOption
>;

function dischargeYValue(count: number, scale: ChartScale): number {
  return scale === "log" ? log1pCount(count) : count;
}

function lightningTooltip(point: LightningPeriod): string {
  return [
    `All discharges: ${point.all_count}`,
    `Cloud-to-ground: ${point.cg_count}`,
    `Lightning days: ${point.lightning_days}`,
    `Max peak current: ${point.max_abs_peak_ka} kA`,
  ].join("<br/>");
}

/** Cloud line + discharge bars. Lightning-day counts stay in the tooltip. */
export function toUnifiedChartOption(
  lightning: LightningPeriod[],
  cloud: CloudPeriod[],
  resolution: Resolution,
  scale: ChartScale = "linear",
  includeCloud = true,
): UnifiedChartOption {
  const useLog = scale === "log";
  const categories = lightning.map((point) => point.period);
  const cloudByPeriod = new Map(cloud.map((point) => [point.period, point]));

  const formatter = (params: { seriesName?: string; dataIndex: number }[]) => {
    const index = params[0]?.dataIndex ?? -1;
    const period = lightning[index];
    if (!period) return "";
    const label = periodLabel(period.period, resolution);
    const lines = [`<strong>${label}</strong>`];
    if (includeCloud) {
      const cloudPoint = cloudByPeriod.get(period.period);
      if (cloudPoint) {
        lines.push(cloudTooltipHtml(cloudPoint, label).replace(`<strong>${label}</strong><br/>`, ""));
      }
    }
    lines.push(lightningTooltip(period));
    return lines.join("<br/>");
  };

  const cloudSeries: LineSeriesOption | null = includeCloud
    ? {
        name: "Mean cloud cover",
        type: "line",
        yAxisIndex: 0,
        connectNulls: false,
        showSymbol: false,
        smooth: 0.15,
        z: 2,
        lineStyle: { width: 2, color: CLOUD_LINE },
        areaStyle: { color: CLOUD_AREA_OVERLAY },
        data: categories.map((period) => cloudByPeriod.get(period)?.mean_cloud_pct ?? null),
      }
    : null;

  const dischargeBars: BarSeriesOption[] = [
    {
      name: "All discharges",
      type: "bar",
      yAxisIndex: 1,
      data: lightning.map((point) => dischargeYValue(point.all_count, scale)),
      itemStyle: barGradient(ALL_TOP, ALL_BOTTOM),
      barCategoryGap: "25%",
    },
    {
      name: "Cloud-to-ground",
      type: "bar",
      yAxisIndex: 1,
      data: lightning.map((point) => dischargeYValue(point.cg_count, scale)),
      itemStyle: barGradient(CG_TOP, CG_BOTTOM),
      barGap: "-100%",
      z: 3,
    },
  ];

  const legendNames = [
    ...(includeCloud ? ["Mean cloud cover"] : []),
    "All discharges",
    "Cloud-to-ground",
  ];

  return {
    animation: false,
    grid: { left: 64, right: 72, top: 48, bottom: 44 },
    legend: { data: legendNames, top: 0, icon: "roundRect" },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "cross" },
      formatter: formatter as TooltipComponentOption["formatter"],
    },
    xAxis: {
      type: "category",
      data: categories,
      ...categoryAxisStyle((period) => tickLabel(period, resolution)),
    },
    yAxis: [
      {
        type: "value",
        name: includeCloud ? "Cloud %" : "",
        min: 0,
        max: CLOUD_PERCENT_AXIS_MAX,
        axisLabel: { color: AXIS_LABEL, formatter: "{value}%" },
        splitLine: { lineStyle: { color: SPLIT_LINE } },
      },
      {
        type: "value",
        name: "Strikes",
        position: "right",
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
        splitLine: { show: false },
      },
    ],
    dataZoom: exploreChartDataZoom(),
    series: [...(cloudSeries ? [cloudSeries] : []), ...dischargeBars],
  };
}
