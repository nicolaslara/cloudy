import type { LineSeriesOption } from "echarts/charts";
import type {
  GridComponentOption,
  LegendComponentOption,
  TooltipComponentOption,
} from "echarts/components";
import type { ComposeOption } from "echarts/core";
import { AXIS_LABEL, AXIS_LINE, CLOUD_LINE, SPLIT_LINE } from "../../lib/chartStyles";
import type { BacktestSeriesPoint } from "./api/predictions";

export type BacktestSeriesOption = ComposeOption<
  | LineSeriesOption
  | GridComponentOption
  | LegendComponentOption
  | TooltipComponentOption
>;

// Reality is the dark solid line the others are judged against; the model's forecast
// is the cloud blue; the seasonal normal is a muted dashed baseline (what the model
// must beat). Skill is "forecast sits closer to actual than normal does", made visible.
const ACTUAL_COLOR = "#334155";
const FORECAST_COLOR = CLOUD_LINE;
const NORMAL_COLOR = AXIS_LINE;

/**
 * The rolling-origin backtest as a time series: for each scored target week, the
 * cloud that actually occurred, the model's forecast, and the seasonal-normal
 * baseline. Three lines on one axis so "does the model track reality better than the
 * flat normal" is read directly — the visual form of the skill number.
 *
 * Static (no dataZoom), like the other normals charts: it's a fixed historical record,
 * not a live feed. Dates label the x-axis; ECharts thins them when the span is long.
 */
export function backtestSeriesOption(points: BacktestSeriesPoint[]): BacktestSeriesOption {
  const weeks = points.map((p) => p.week);
  const pct = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v)}%`);

  const dot = (color: string) =>
    `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${color};margin-right:6px"></span>`;
  const formatter = (params: { dataIndex: number }[]) => {
    const index = params[0]?.dataIndex ?? -1;
    const point = points[index];
    if (!point) return "";
    return [
      `<strong>${point.week}</strong>`,
      `${dot(ACTUAL_COLOR)}Actual: ${pct(point.actual)}`,
      `${dot(FORECAST_COLOR)}Forecast: ${pct(point.forecast)}`,
      `${dot(NORMAL_COLOR)}Seasonal normal: ${pct(point.normal)}`,
    ].join("<br/>");
  };

  const line = (
    name: string,
    color: string,
    data: number[],
    dashed = false,
  ): LineSeriesOption => ({
    name,
    type: "line",
    showSymbol: false,
    smooth: 0.1,
    lineStyle: { width: dashed ? 1.5 : 2, color, type: dashed ? "dashed" : "solid" },
    itemStyle: { color },
    data,
  });

  return {
    animation: false,
    grid: { left: 44, right: 16, top: 28, bottom: 32 },
    legend: { top: 0, textStyle: { color: AXIS_LABEL } },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "line" },
      formatter: formatter as TooltipComponentOption["formatter"],
    },
    xAxis: {
      type: "category",
      data: weeks,
      axisLabel: { color: AXIS_LABEL },
      axisLine: { lineStyle: { color: AXIS_LINE } },
    },
    yAxis: {
      type: "value",
      min: 0,
      max: 100,
      axisLabel: { color: AXIS_LABEL, formatter: "{value}%" },
      splitLine: { lineStyle: { color: SPLIT_LINE } },
    },
    series: [
      line(
        "Actual",
        ACTUAL_COLOR,
        points.map((p) => p.actual),
      ),
      line(
        "Forecast",
        FORECAST_COLOR,
        points.map((p) => p.forecast),
      ),
      line(
        "Seasonal normal",
        NORMAL_COLOR,
        points.map((p) => p.normal),
        true,
      ),
    ],
  };
}

/**
 * The same backtest as an error chart: rolling 52-week mean absolute error of the
 * seasonal normal versus the model. The per-week gain is hard to see in the overlaid
 * lines above; here the model line sitting below the normal line *is* the skill.
 */
export function backtestErrorOption(points: BacktestSeriesPoint[]): BacktestSeriesOption {
  const window = 52;
  const weeks = points.map((p) => p.week);
  const roll = (errs: number[]) =>
    errs.map((_, i) => {
      const slice = errs.slice(Math.max(0, i - window + 1), i + 1);
      return slice.reduce((a, b) => a + b, 0) / slice.length;
    });
  const normalErr = roll(points.map((p) => Math.abs(p.actual - p.normal)));
  const modelErr = roll(points.map((p) => Math.abs(p.actual - p.forecast)));

  const dot = (color: string) =>
    `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${color};margin-right:6px"></span>`;
  const formatter = (params: { dataIndex: number }[]) => {
    const i = params[0]?.dataIndex ?? -1;
    const ne = normalErr[i];
    const me = modelErr[i];
    if (ne == null || me == null) return "";
    return [
      `<strong>${weeks[i]}</strong>`,
      `${dot(NORMAL_COLOR)}Seasonal normal error: ${ne.toFixed(1)} pp`,
      `${dot(FORECAST_COLOR)}Model error: ${me.toFixed(1)} pp`,
    ].join("<br/>");
  };

  return {
    animation: false,
    grid: { left: 48, right: 16, top: 28, bottom: 32 },
    legend: { top: 0, textStyle: { color: AXIS_LABEL } },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "line" },
      formatter: formatter as TooltipComponentOption["formatter"],
    },
    xAxis: {
      type: "category",
      data: weeks,
      axisLabel: { color: AXIS_LABEL },
      axisLine: { lineStyle: { color: AXIS_LINE } },
    },
    yAxis: {
      type: "value",
      min: 0,
      name: "mean abs error (cloud %)",
      nameLocation: "middle",
      nameGap: 34,
      nameTextStyle: { color: AXIS_LABEL },
      axisLabel: { color: AXIS_LABEL },
      splitLine: { lineStyle: { color: SPLIT_LINE } },
    },
    series: [
      {
        name: "Seasonal normal error",
        type: "line",
        showSymbol: false,
        smooth: 0.1,
        lineStyle: { width: 2, color: NORMAL_COLOR },
        itemStyle: { color: NORMAL_COLOR },
        data: normalErr.map((v) => Number(v.toFixed(2))),
      },
      {
        name: "Model error",
        type: "line",
        showSymbol: false,
        smooth: 0.1,
        lineStyle: { width: 2, color: FORECAST_COLOR },
        itemStyle: { color: FORECAST_COLOR },
        data: modelErr.map((v) => Number(v.toFixed(2))),
      },
    ],
  };
}
