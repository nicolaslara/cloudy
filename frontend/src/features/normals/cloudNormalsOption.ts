import type { BarSeriesOption } from "echarts/charts";
import type { GridComponentOption, TooltipComponentOption } from "echarts/components";
import type { ComposeOption } from "echarts/core";
import { AXIS_LABEL, SPLIT_LINE, categoryAxisStyle } from "../../lib/chartStyles";
import type { CloudNormalPoint, NormalsPeriod } from "./api/climatology";
import { normalsPeriodLabel } from "./periodLabel";

export type CloudNormalsOption = ComposeOption<
  BarSeriesOption | GridComponentOption | TooltipComponentOption
>;

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
 */
export function cloudNormalsOption(
  series: CloudNormalPoint[],
  grain: NormalsPeriod,
): CloudNormalsOption {
  const categories = series.map((point) => normalsPeriodLabel(point.period, grain));

  const formatter = (params: { dataIndex: number }[]) => {
    const point = series[params[0]?.dataIndex ?? -1];
    if (!point) return "";
    const pct = (v: number | null) => (v == null ? "—" : `${Math.round(v)}%`);
    const years = `${point.year_count} year${point.year_count === 1 ? "" : "s"}`;
    return [
      `<strong>${normalsPeriodLabel(point.period, grain)}</strong>`,
      `Normal cloud cover: ${pct(point.mean_cloud_pct)}`,
      `<span style="color:#7b8794">clear ${pct(point.clear_pct)} · partly ${pct(point.partial_pct)} · overcast ${pct(point.overcast_pct)}</span>`,
      `<span style="color:#7b8794">over ${years}</span>`,
    ].join("<br/>");
  };

  return {
    animation: false,
    grid: { left: 48, right: 16, top: 16, bottom: 32 },
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
    series: [
      {
        name: "Normal cloud cover",
        type: "bar",
        // Round the top corners and shade each bar by its own cloudiness.
        itemStyle: { borderRadius: [4, 4, 0, 0] },
        data: series.map((point) => ({
          value: point.mean_cloud_pct,
          itemStyle: { color: cloudColor(point.mean_cloud_pct) },
        })),
      },
    ],
  };
}
