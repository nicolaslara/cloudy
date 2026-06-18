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
import { CLOUD_PERCENT_AXIS_MAX, countAxisMax, logCountAxisMax } from "../../../lib/chartAxis";
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
} from "../../../lib/chartStyles";
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

/**
 * Cloud line + discharge bars on one chart with two y-axes: cloud % on the left
 * (axis 0), strike counts on the right (axis 1). The x-axis categories come from
 * the lightning series — cloud is joined by period key, so a cloud-less period
 * still renders its bars and just shows a null line point. `includeCloud=false`
 * drops the line, its axis label, and its legend/tooltip entries entirely.
 * Lightning-day counts live only in the tooltip, not as a series.
 */
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
        // Reuse the cloud tooltip body but strip its repeated header — this
        // unified tooltip already prints the period label once above.
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
        // Cloud draws against the edge-to-edge twin x-axis (index 1, boundaryGap
        // false) so the filled area meets both frame edges instead of floating a
        // half-bucket in from each side. The bars stay on axis 0 (boundaryGap
        // true) so the first/last bucket isn't sliced in half at the frame.
        xAxisIndex: 1,
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
    // Two category x-axes over the same buckets. Axis 0 is the visible one and
    // carries the bars with the default boundaryGap (bars sit centred in their
    // bucket, edges intact). Axis 1 is an invisible twin with boundaryGap:false
    // that only the cloud line/area rides, so the curve spans the full width.
    // They share categories, so the inside dataZoom (which auto-links parallel
    // x-axes in a grid) pans and zooms both together. The twin axis is omitted
    // when there's no cloud line to avoid a dangling unused axis.
    xAxis: [
      {
        type: "category",
        data: categories,
        ...categoryAxisStyle((period) => tickLabel(period, resolution)),
      },
      ...(includeCloud
        ? [
            {
              type: "category" as const,
              data: categories,
              boundaryGap: false,
              show: false,
              // It's a layout-only helper, so keep it out of the crosshair: the
              // shared tooltip already labels the bucket off axis 0, and a second
              // x pointer here would just print the period twice.
              axisPointer: { show: false },
            },
          ]
        : []),
    ],
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
