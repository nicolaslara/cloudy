import type { BarSeriesOption, LineSeriesOption } from "echarts/charts";
import type {
  GridComponentOption,
  LegendComponentOption,
  TooltipComponentOption,
} from "echarts/components";
import type { ComposeOption } from "echarts/core";
import { AXIS_LABEL, SPLIT_LINE, categoryAxisStyle } from "../../lib/chartStyles";
import type { CloudNormalPoint, NormalsPeriod } from "./api/climatology";
import type { CloudCurve } from "./cloudComparisonOption";
import { normalsPeriodLabel } from "./periodLabel";

export type CloudNormalsOption = ComposeOption<
  | BarSeriesOption
  | LineSeriesOption
  | GridComponentOption
  | LegendComponentOption
  | TooltipComponentOption
>;

// The station bar's legend name when point-estimate overlays share the chart, so the
// three read as one toggleable set: the station normal, then the sharper estimates.
const STATION_NAME = "Nearest station";

// The bar is coloured by its own value: a clear-sky blue at 0% sliding to slate at
// 100%, so cloudiness reads twice — once as height, once as shade. The endpoints
// match the sky-state palette elsewhere in the view.
const CLEAR_RGB = [159, 198, 245] as const; // #9fc6f5
const OVERCAST_RGB = [86, 98, 117] as const; // #566275

function cloudColor(meanPct: number | null): string {
  const t = Math.min(1, Math.max(0, (meanPct ?? 0) / 100));
  const mix = (a: number, b: number) => Math.round(a + (b - a) * t);
  const [cr, cg, cb] = CLEAR_RGB;
  const [or, og, ob] = OVERCAST_RGB;
  return `rgb(${mix(cr, or)}, ${mix(cg, og)}, ${mix(cb, ob)})`;
}

/**
 * Cloud normal as one bar per slot whose height is the *average* cloud cover —
 * the direct answer to "how cloudy is this place in this month, typically". That
 * single number is what a climatology normal means (the brief's
 * expected_cloud_for_month), so it's the headline.
 *
 * The average alone hides that Swedish cloud is U-shaped (an hour is usually near
 * clear or near overcast, rarely the mean), so the clear/partly/overcast split
 * rides in the tooltip — there for the curious, not crowding out the answer.
 *
 * `overlays` (optional) draws the point estimators — e.g. the kNN average — as
 * lines on the same axis, with a legend so any curve (the station bar included) can
 * be toggled to compare. With no overlays it's the plain headline bar it always was.
 */
export function cloudNormalsOption(
  series: CloudNormalPoint[],
  grain: NormalsPeriod,
  overlays: CloudCurve[] = [],
): CloudNormalsOption {
  const categories = series.map((point) => normalsPeriodLabel(point.period, grain));
  const hasOverlays = overlays.length > 0;
  // When estimators share the chart the bar is one curve among three, so it takes the
  // "Nearest station" name; alone it keeps its headline title.
  const barName = hasOverlays ? STATION_NAME : "Normal cloud cover";

  const pct = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v)}%`);
  const formatter = (params: { dataIndex: number }[]) => {
    const index = params[0]?.dataIndex ?? -1;
    const point = series[index];
    if (!point) return "";
    const years = `${point.year_count} year${point.year_count === 1 ? "" : "s"}`;
    const dot = (color: string) =>
      `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${color};margin-right:6px"></span>`;
    const rows = [
      `<strong>${normalsPeriodLabel(point.period, grain)}</strong>`,
      `${barName}: ${pct(point.mean_cloud_pct)}`,
      // Each overlay's value for this month, dot-coloured to match its line.
      ...overlays.map((curve) => `${dot(curve.color)}${curve.name}: ${pct(curve.monthly[index])}`),
      `<span style="color:#7b8794">clear ${pct(point.clear_pct)} · partly ${pct(point.partial_pct)} · overcast ${pct(point.overcast_pct)}</span>`,
      `<span style="color:#7b8794">over ${years}</span>`,
    ];
    return rows.join("<br/>");
  };

  const barSeries: BarSeriesOption = {
    name: barName,
    type: "bar",
    // Round the top corners and shade each bar by its own cloudiness.
    itemStyle: { borderRadius: [4, 4, 0, 0] },
    data: series.map((point) => ({
      value: point.mean_cloud_pct,
      itemStyle: { color: cloudColor(point.mean_cloud_pct) },
    })),
  };

  const lineSeries: LineSeriesOption[] = overlays.map((curve) => ({
    name: curve.name,
    type: "line",
    connectNulls: false,
    showSymbol: false,
    smooth: 0.15,
    lineStyle: { width: 2, color: curve.color },
    itemStyle: { color: curve.color },
    data: curve.monthly,
  }));

  return {
    animation: false,
    // Leave room at the top for the legend only when there's one to show.
    grid: { left: 48, right: 16, top: hasOverlays ? 28 : 16, bottom: 32 },
    ...(hasOverlays ? { legend: { top: 0, textStyle: { color: AXIS_LABEL } } } : {}),
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: formatter as TooltipComponentOption["formatter"],
    },
    xAxis: {
      type: "category",
      data: categories,
      ...categoryAxisStyle((value) => value),
    },
    yAxis: {
      type: "value",
      min: 0,
      max: 100,
      axisLabel: { color: AXIS_LABEL, formatter: "{value}%" },
      splitLine: { lineStyle: { color: SPLIT_LINE } },
    },
    series: [barSeries, ...lineSeries],
  };
}
