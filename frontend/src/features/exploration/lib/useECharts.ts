import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { BarChart, LineChart } from "echarts/charts";
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
// This is the exploration lab's chart hook: it speaks the feature's own zoom/option
// vocabulary (the dataZoom slider, calendar-window translation), so it lives inside
// the feature beside the modules it leans on. The Normals deliverable deliberately
// does NOT use this — it draws through the generic lib/useChart — which is what keeps
// the deliverable free of exploration code.
import { parseUtcMs, readZoomRange, snapRangeToCategories } from "./chartZoom";
import type { ChartOption } from "./chartOption";
import type { CloudChartOption } from "./cloudChartOption";
import type { UnifiedChartOption } from "./unifiedChartOption";
import { readVisibleZoom, type VisibleZoom } from "./lightningExplorer";
import type { Resolution } from "../api/lightning";

echarts.use([
  BarChart,
  LineChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
  CanvasRenderer,
]);

// Components we replace (not deep-merge) on a display-only patch. replaceMerge
// avoids stale leftovers when, e.g., a series or legend entry disappears between
// renders — a plain merge would keep the old one around.
const DISPLAY_REPLACE = ["series", "yAxis", "legend", "tooltip", "xAxis"] as const;

export type AnyChartOption = ChartOption | CloudChartOption | UnifiedChartOption;

function axisConfig(option: AnyChartOption): {
  type: "category" | "time";
  categories: string[];
  timeBounds?: { min: string; max: string };
} {
  const axis = Array.isArray(option.xAxis) ? option.xAxis[0] : option.xAxis;
  const typed = axis as { type?: string; data?: string[]; min?: string; max?: string } | undefined;
  if (typed?.type === "time" && typed.min != null && typed.max != null) {
    const min =
      typeof typed.min === "number"
        ? new Date(typed.min).toISOString().slice(0, 10)
        : String(typed.min).slice(0, 10);
    const max =
      typeof typed.max === "number"
        ? new Date(typed.max).toISOString().slice(0, 10)
        : String(typed.max).slice(0, 10);
    return { type: "time", categories: [], timeBounds: { min, max } };
  }
  return { type: "category", categories: typed?.data ?? [] };
}

type DataZoomState = {
  type?: string;
  start?: number;
  end?: number;
  startValue?: string | number;
  endValue?: string | number;
}[];

export type EChartsHandle = {
  containerRef: React.RefObject<HTMLDivElement | null>;
  chartRef: React.RefObject<echarts.ECharts | null>;
  /** Last zoom this chart emitted — lets owners skip echoing it back (drag fights). */
  lastEmittedRef: React.RefObject<VisibleZoom | null>;
};

const EMIT_DEBOUNCE_MS = 150; // let a drag settle before state/queries react

/**
 * Mount an ECharts instance on the returned ref; re-applies `option` when it changes.
 *
 * The central decision here is rebuild-vs-patch. `structureKey` identifies a new
 * chart context (history span + granularity); when it changes we hard-reset the
 * option (notMerge) because the axis categories themselves changed. When only
 * the data/display changed (new location, log toggle), we patch series and axes
 * in place and *carry the user's zoom across* by reading their visible calendar
 * window before the patch and re-dispatching it after — otherwise every refetch
 * would yank the view back to full range.
 */
export function useECharts(
  option: AnyChartOption | null,
  structureKey = "",
  onVisibleZoom?: (zoom: VisibleZoom) => void,
  debugKey: "chart" | "timeSlider" = "chart",
  resolution?: Resolution,
): EChartsHandle {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const prevStructureKey = useRef<string | null>(null);
  const lastEmittedRef = useRef<VisibleZoom | null>(null);
  const onVisibleZoomRef = useRef(onVisibleZoom);
  useEffect(() => {
    onVisibleZoomRef.current = onVisibleZoom;
  });

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const chart = echarts.init(container);
    chartRef.current = chart;
    if (import.meta.env.DEV) {
      if (debugKey === "timeSlider") {
        (window as Window & { __cloudyTimeSlider?: echarts.ECharts }).__cloudyTimeSlider = chart;
      } else {
        (window as Window & { __cloudyChart?: echarts.ECharts }).__cloudyChart = chart;
      }
    }

    const emitVisibleZoom = () => {
      if (!onVisibleZoomRef.current) return;
      const current = chart.getOption() as AnyChartOption;
      const axis = axisConfig(current);
      const zoom = readVisibleZoom(
        axis.categories,
        current.dataZoom as DataZoomState,
        axis.timeBounds,
        resolution,
      );
      if (zoom) {
        lastEmittedRef.current = zoom;
        onVisibleZoomRef.current(zoom);
      }
    };

    let emitTimer: ReturnType<typeof setTimeout> | undefined;
    const debouncedEmit = () => {
      clearTimeout(emitTimer);
      emitTimer = setTimeout(emitVisibleZoom, EMIT_DEBOUNCE_MS);
    };

    chart.on("datazoom", debouncedEmit);

    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(container);
    return () => {
      clearTimeout(emitTimer);
      chart.off("datazoom", debouncedEmit);
      observer.disconnect();
      chart.dispose();
      chartRef.current = null;
      prevStructureKey.current = null;
      if (import.meta.env.DEV) {
        if (debugKey === "timeSlider") {
          delete (window as Window & { __cloudyTimeSlider?: echarts.ECharts }).__cloudyTimeSlider;
        } else {
          delete (window as Window & { __cloudyChart?: echarts.ECharts }).__cloudyChart;
        }
      }
    };
  }, [debugKey, resolution]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!option || !chart) return;

    const structuralChange = prevStructureKey.current !== structureKey;
    prevStructureKey.current = structureKey;

    const emitVisibleZoom = () => {
      if (!onVisibleZoomRef.current) return;
      const current = chart.getOption() as AnyChartOption;
      const axis = axisConfig(current);
      const zoom = readVisibleZoom(
        axis.categories,
        current.dataZoom as DataZoomState,
        axis.timeBounds,
        resolution,
      );
      if (zoom) {
        lastEmittedRef.current = zoom;
        onVisibleZoomRef.current(zoom);
      }
    };

    if (structuralChange) {
      chart.setOption(option, { notMerge: true });
      // Zoom is synced from React state in chart panes — do not emit the
      // chart's default full-range zoom here (it fights the slider).
      return;
    }

    const prev = chart.getOption() as AnyChartOption;
    const prevAxis = axisConfig(prev);
    const nextAxis = axisConfig(option);
    const zoomRange = readZoomRange(
      prevAxis.categories,
      prev.dataZoom as DataZoomState,
      prevAxis.timeBounds,
      resolution,
    );

    chart.setOption(
      {
        legend: option.legend,
        tooltip: option.tooltip,
        yAxis: option.yAxis,
        xAxis: option.xAxis,
        series: option.series,
      },
      { replaceMerge: [...DISPLAY_REPLACE] },
    );

    if (!zoomRange) return;

    // Restoring zoom must wait a frame: the setOption patch above hasn't laid
    // out the new axis yet, so dispatching dataZoom synchronously would snap
    // against stale geometry. rAF lets the new option settle first.
    if (nextAxis.type === "time" && nextAxis.timeBounds) {
      requestAnimationFrame(() => {
        // Drive both dataZoom entries (inside + slider) so they stay in lockstep.
        for (const dataZoomIndex of [0, 1]) {
          chart.dispatchAction({
            type: "dataZoom",
            dataZoomIndex,
            startValue: parseUtcMs(zoomRange.startDay),
            endValue: parseUtcMs(zoomRange.endDay),
          });
        }
        emitVisibleZoom();
      });
      return;
    }

    if (nextAxis.categories.length > 0) {
      const { startValue, endValue } = snapRangeToCategories(
        zoomRange,
        nextAxis.categories,
        resolution,
      );
      requestAnimationFrame(() => {
        for (const dataZoomIndex of [0, 1]) {
          chart.dispatchAction({ type: "dataZoom", dataZoomIndex, startValue, endValue });
        }
        emitVisibleZoom();
      });
    }
  }, [option, structureKey, resolution]);

  return { containerRef, chartRef, lastEmittedRef };
}
