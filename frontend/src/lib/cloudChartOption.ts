import type { LineSeriesOption } from "echarts/charts";
import type {
  DataZoomComponentOption,
  GridComponentOption,
  TooltipComponentOption,
} from "echarts/components";
import type { ComposeOption } from "echarts/core";
import type { CloudPeriod } from "../api/cloud";
import type { Resolution } from "../api/lightning";
import { CLOUD_PERCENT_AXIS_MAX } from "./chartAxis";
import { exploreChartDataZoom } from "./chartOption";
import {
  AXIS_LABEL,
  CLOUD_AREA_SOLO,
  CLOUD_LINE,
  SPLIT_LINE,
  categoryAxisStyle,
} from "./chartStyles";
import { cloudTooltipHtml } from "./cloudSeries";
import { periodLabel, tickLabel } from "./series";

export type CloudChartOption = ComposeOption<
  | LineSeriesOption
  | GridComponentOption
  | TooltipComponentOption
  | DataZoomComponentOption
>;

export function toCloudChartOption(
  series: CloudPeriod[],
  resolution: Resolution,
): CloudChartOption {
  const categories = series.map((point) => point.period);
  const formatter = (params: { dataIndex: number }[]) => {
    const point = series[params[0]?.dataIndex ?? -1];
    return point ? cloudTooltipHtml(point, periodLabel(point.period, resolution)) : "";
  };

  return {
    animation: false,
    grid: { left: 64, right: 24, top: 24, bottom: 44 },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "line" },
      formatter: formatter as TooltipComponentOption["formatter"],
    },
    xAxis: {
      type: "category",
      data: categories,
      ...categoryAxisStyle((period) => tickLabel(period, resolution)),
    },
    yAxis: {
      type: "value",
      min: 0,
      max: CLOUD_PERCENT_AXIS_MAX,
      axisLabel: { color: AXIS_LABEL, formatter: "{value}%" },
      splitLine: { lineStyle: { color: SPLIT_LINE } },
    },
    dataZoom: exploreChartDataZoom(),
    series: [
      {
        name: "Mean cloud cover",
        type: "line",
        connectNulls: false,
        showSymbol: false,
        smooth: 0.15,
        lineStyle: { width: 2, color: CLOUD_LINE },
        areaStyle: { color: CLOUD_AREA_SOLO },
        data: series.map((point) => point.mean_cloud_pct),
      },
    ],
  };
}
