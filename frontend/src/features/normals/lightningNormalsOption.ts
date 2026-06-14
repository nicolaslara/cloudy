import type { BarSeriesOption } from "echarts/charts";
import type { GridComponentOption, TooltipComponentOption } from "echarts/components";
import type { ComposeOption } from "echarts/core";
import {
  ALL_BOTTOM,
  ALL_TOP,
  AXIS_LABEL,
  SPLIT_LINE,
  barGradient,
  categoryAxisStyle,
} from "../../lib/chartStyles";
import type { LightningNormalPoint, NormalsPeriod } from "./api/climatology";
import { normalsPeriodLabel } from "./periodLabel";

export type LightningNormalsOption = ComposeOption<
  BarSeriesOption | GridComponentOption | TooltipComponentOption
>;

/**
 * Pure ECharts option for the lightning normal: bars of strike-day probability
 * (the chance any given day in a slot sees a nearby discharge — SMHI's
 * thunder-day notion). Probability is the headline because it's bounded 0–100%
 * and reads as "how likely", while the raw expected-days count lives in the
 * tooltip for anyone who wants incidence rather than likelihood.
 */
export function lightningNormalsOption(
  series: LightningNormalPoint[],
  grain: NormalsPeriod,
): LightningNormalsOption {
  const categories = series.map((point) => normalsPeriodLabel(point.period, grain));

  // strike_day_probability arrives as a 0–1 fraction; the axis speaks percent.
  const bars = series.map((point) =>
    point.strike_day_probability == null ? null : point.strike_day_probability * 100,
  );

  const formatter = (params: { dataIndex: number }[]) => {
    const point = series[params[0]?.dataIndex ?? -1];
    if (!point) return "";
    const pct =
      point.strike_day_probability == null
        ? "—"
        : `${Math.round(point.strike_day_probability * 100)}%`;
    const days =
      point.expected_lightning_days == null
        ? "—"
        : point.expected_lightning_days.toFixed(1);
    return [
      `<strong>${normalsPeriodLabel(point.period, grain)}</strong>`,
      `Chance of a strike day: ${pct}`,
      `Expected lightning days: ${days}`,
      `Based on ${point.year_count} year${point.year_count === 1 ? "" : "s"}`,
    ].join("<br/>");
  };

  return {
    animation: false,
    grid: { left: 56, right: 24, top: 24, bottom: 36 },
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
      // Strike-day probability is small almost everywhere in Sweden (a few percent,
      // ~10% at the July peak), so a fixed 0–100% axis would crush every bar to a
      // sliver. Let ECharts fit the axis to the data; the % label keeps it honest
      // that these are still probabilities, not counts.
      type: "value",
      min: 0,
      axisLabel: { color: AXIS_LABEL, formatter: "{value}%" },
      splitLine: { lineStyle: { color: SPLIT_LINE } },
    },
    series: [
      {
        name: "Chance of a strike day",
        type: "bar",
        itemStyle: barGradient(ALL_TOP, ALL_BOTTOM),
        data: bars,
      },
    ],
  };
}
