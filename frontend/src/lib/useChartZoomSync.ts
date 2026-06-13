import { useEffect, type RefObject } from "react";
import type { ECharts } from "echarts/core";
import type { Resolution } from "../api/lightning";
import { snapRangeToCategories } from "./chartZoom";
import {
  readVisibleZoom,
  visibleZoomToCalendarRange,
  type VisibleZoom,
} from "./lightningExplorer";

/**
 * The three chart panes (lightning, cloud, unified) all need to push the parent's
 * `visibleZoom` *down* into their echarts instance — but echarts also pushes user
 * drags *up* via the same `onVisibleZoom` callback. Left unguarded those two
 * directions form a feedback loop: we re-apply the zoom the user just produced,
 * which re-emits, which we re-apply… The `lastEmittedRef` is how we break it —
 * useECharts stamps it with whatever the chart last told us, and we skip
 * re-applying a window the chart already owns. This was copy-pasted in all three
 * panes; it lives here now so the dance has exactly one author.
 *
 * `categories` is the pane's filled period axis (each pane derives it from its own
 * series), so this hook stays agnostic to lightning-vs-cloud shapes.
 */
export function useChartZoomSync({
  chartRef,
  lastEmittedRef,
  categories,
  visibleZoom,
  resolution,
}: {
  chartRef: RefObject<ECharts | null>;
  // Optional because the test harness mocks useECharts without it; a missing ref
  // just means "never skip", which is safe when there's no real chart to fight.
  lastEmittedRef?: RefObject<VisibleZoom | null>;
  categories: string[];
  visibleZoom: VisibleZoom;
  resolution: Resolution;
}) {
  const { startPeriod, endPeriod } = visibleZoom;
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || categories.length === 0) return;
    // Skip echoing the chart's own drag back at it (it would fight the user).
    const emitted = lastEmittedRef?.current;
    if (emitted && emitted.startPeriod === startPeriod && emitted.endPeriod === endPeriod) {
      return;
    }

    const { startValue, endValue } = snapRangeToCategories(
      visibleZoomToCalendarRange({ startPeriod, endPeriod }, resolution),
      categories,
      resolution,
    );
    const current = readVisibleZoom(
      categories,
      chart.getOption().dataZoom as Parameters<typeof readVisibleZoom>[1],
      undefined,
      resolution,
    );
    if (current?.startPeriod === startValue && current?.endPeriod === endValue) return;

    requestAnimationFrame(() => {
      for (const dataZoomIndex of [0, 1]) {
        chart.dispatchAction({ type: "dataZoom", dataZoomIndex, startValue, endValue });
      }
    });
    // categories changes whenever the data/resolution does, so it covers the
    // axis identity; the rest are the inputs that move the window.
  }, [startPeriod, endPeriod, categories, chartRef, lastEmittedRef, resolution]);
}
