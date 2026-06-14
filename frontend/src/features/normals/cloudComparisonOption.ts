import type { LineSeriesOption } from "echarts/charts";
import type {
  GridComponentOption,
  LegendComponentOption,
  TooltipComponentOption,
} from "echarts/components";
import type { ComposeOption } from "echarts/core";

export type CloudComparisonOption = ComposeOption<
  | LineSeriesOption
  | GridComponentOption
  | TooltipComponentOption
  | LegendComponentOption
>;

// One model's normal curve over the twelve-month axis: a name for the legend, a
// colour to tell it apart, and the per-month mean cloud (null where the model has
// no answer for that month, so the line breaks instead of bridging a gap).
export type CloudCurve = {
  name: string;
  color: string;
  // Index i is month i+1; null is a genuine gap, not zero cloud.
  monthly: (number | null)[];
};
