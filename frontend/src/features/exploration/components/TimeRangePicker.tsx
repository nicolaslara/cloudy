import { useEffect, useMemo } from "react";
import type { Resolution } from "../api/lightning";
import { readZoomRange, snapRangeToCategories } from "../lib/chartZoom";
import { toTimeRangeOption } from "../lib/chartOption";
import {
  formatVisibleZoomLabel,
  readVisibleZoom,
  visibleZoomToCalendarRange,
  type VisibleZoom,
} from "../lib/lightningExplorer";
import { useECharts } from "../lib/useECharts";

// The shared time slider: a small overview chart whose dataZoom is the single
// source of truth for the visible window across every pane. Other panes mirror
// `visibleZoom`; this one both emits it (on drag) and is driven by it (when
// changed elsewhere) — hence the careful echo-suppression in the effect below.
export function TimeRangePicker({
  periods,
  counts,
  resolution,
  visibleZoom,
  label,
  structureKey,
  onVisibleZoom,
}: {
  periods: string[];
  counts: number[];
  resolution: Resolution;
  visibleZoom: VisibleZoom;
  label?: string;
  structureKey: string;
  onVisibleZoom: (zoom: VisibleZoom) => void;
}) {
  const option = useMemo(
    () => toTimeRangeOption(periods, counts, resolution),
    [periods, counts, resolution],
  );

  const { containerRef, chartRef, lastEmittedRef } = useECharts(
    option,
    structureKey,
    onVisibleZoom,
    "timeSlider",
    resolution,
  );

  const { startPeriod, endPeriod } = visibleZoom;
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || periods.length === 0) return;
    // This zoom originated from this chart's own drag — echoing it back would
    // fight the user's hand (the "slider snaps back" bug).
    const emitted = lastEmittedRef.current;
    if (emitted && emitted.startPeriod === startPeriod && emitted.endPeriod === endPeriod) {
      return;
    }

    const { startValue, endValue } = snapRangeToCategories(
      visibleZoomToCalendarRange({ startPeriod, endPeriod }, resolution),
      periods,
      resolution,
    );
    // Skip if the chart is already at this window — re-dispatching dataZoom we're
    // already showing causes a visible flicker for no gain.
    const current = readVisibleZoom(
      periods,
      chart.getOption().dataZoom as Parameters<typeof readZoomRange>[1],
      undefined,
      resolution,
    );
    if (current?.startPeriod === startValue && current?.endPeriod === endValue) return;

    // rAF defers the dispatch past ECharts' own render so the action lands on a
    // settled chart; both dataZoom components (inside slider + the chart's own)
    // must be moved together or they desync.
    requestAnimationFrame(() => {
      for (const dataZoomIndex of [0, 1]) {
        chart.dispatchAction({ type: "dataZoom", dataZoomIndex, startValue, endValue });
      }
    });
  }, [startPeriod, endPeriod, structureKey, periods, chartRef, lastEmittedRef, resolution]);

  return (
    <div className="time-range-picker">
      <div className="time-range-picker-head">
        <span>Time range</span>
        <span className="time-range-picker-label">{label ?? formatVisibleZoomLabel(visibleZoom)}</span>
      </div>
      <div ref={containerRef} className="time-range-picker-canvas" />
    </div>
  );
}
