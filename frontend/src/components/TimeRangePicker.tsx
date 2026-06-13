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
    const current = readVisibleZoom(
      periods,
      chart.getOption().dataZoom as Parameters<typeof readZoomRange>[1],
      undefined,
      resolution,
    );
    if (current?.startPeriod === startValue && current?.endPeriod === endValue) return;

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
