import type { BarSeriesOption } from "echarts/charts";

// The whole charting surface shares one quiet, slightly cool gray palette so the
// lightning chart, the cloud chart, and the unified overlay feel like one
// instrument rather than three. The grays are deliberately ranked by how loud
// each element should be: axis *labels* carry meaning so they're the darkest
// readable gray; the axis *line* is structural but secondary, so it's lighter;
// the split lines are just a reading aid behind the data, so they're nearly
// invisible. Keeping them here means a single edit re-tunes every chart at once,
// and stops the three builders from drifting apart over time.
export const AXIS_LABEL = "#52606d"; // darkest — labels carry the numbers/dates
export const AXIS_LINE = "#9aa5b1"; // lighter — structural, not the focus
export const SPLIT_LINE = "#eef2f6"; // faint — gridlines sit behind the data

// Discharge bars. Blue is the full population of strikes; warm amber is the
// cloud-to-ground subset, which is the dangerous one and so gets the attention
// color. Each pair is a top→bottom gradient (see barGradient) — the brighter top
// catches the eye while the paler bottom keeps the bar grounded.
export const ALL_TOP = "#7b93d8";
export const ALL_BOTTOM = "#b9c9ee";
export const CG_TOP = "#e8930c";
export const CG_BOTTOM = "#f6c161";

// Cloud cover is drawn as a line with a translucent fill in the same blue family
// as the "All discharges" bars, so cloud reads as ambient context rather than a
// competing signal. The standalone cloud chart wants a touch more presence than
// the unified overlay (where bars dominate), hence two area opacities.
export const CLOUD_LINE = "#5b76c9";
export const CLOUD_AREA_SOLO = "rgba(91, 118, 201, 0.18)";
export const CLOUD_AREA_OVERLAY = "rgba(91, 118, 201, 0.12)";

/**
 * A vertical top→bottom fill for a bar. The gradient is the chart's main bit of
 * visual texture: it gives flat count bars a sense of light and volume without
 * adding chartjunk, and the rounded top edge keeps dense histograms from reading
 * as a solid wall. Top is the saturated end, bottom the pale end.
 */
export function barGradient(top: string, bottom: string): BarSeriesOption["itemStyle"] {
  return {
    borderRadius: [3, 3, 0, 0],
    color: {
      type: "linear",
      x: 0,
      y: 0,
      x2: 0,
      y2: 1,
      colorStops: [
        { offset: 0, color: top },
        { offset: 1, color: bottom },
      ],
    },
  };
}

/**
 * The shared category-x-axis styling (tick-aligned labels in the label gray, a
 * structural axis line). Callers pass their own label `formatter` because the
 * label *text* is domain-specific (period vs. tick formatting) even though the
 * *look* is identical everywhere.
 */
export function categoryAxisStyle(
  formatter: (value: string) => string,
): {
  axisLabel: { formatter: (value: string) => string; color: string };
  axisTick: { alignWithLabel: true };
  axisLine: { lineStyle: { color: string } };
} {
  return {
    axisLabel: { formatter, color: AXIS_LABEL },
    axisTick: { alignWithLabel: true },
    axisLine: { lineStyle: { color: AXIS_LINE } },
  };
}
