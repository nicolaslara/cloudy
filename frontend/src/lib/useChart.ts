import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { BarChart, LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([BarChart, LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer]);

// On a data update we replace these whole — never deep-merge — so a series or
// legend entry that vanishes between renders doesn't linger from the old option.
const DISPLAY_REPLACE = ["series", "yAxis", "xAxis", "legend", "tooltip"] as const;

/**
 * The generic chart mount for *static* figures — the Normals view and anything
 * else that draws a fixed picture with no zoom/brush interaction. It is the
 * deliverable's chart primitive and depends on nothing but ECharts, which is
 * exactly what lets Normals stay independent of the exploration lab. The lab has
 * its own zoom-aware hook (features/exploration/lib/useECharts) — do not reach for
 * that here.
 *
 * `structureKey` is the rebuild signal: when it changes the axes themselves have
 * changed (different period, different location shape), so we hard-reset with
 * notMerge; otherwise we patch series/axes in place.
 */
export function useChart<TOption>(option: TOption | null, structureKey = "") {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const prevStructureKey = useRef<string | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const chart = echarts.init(container);
    chartRef.current = chart;
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(container);
    return () => {
      observer.disconnect();
      chart.dispose();
      chartRef.current = null;
      prevStructureKey.current = null;
    };
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    if (!option || !chart) return;
    const structural = prevStructureKey.current !== structureKey;
    prevStructureKey.current = structureKey;
    if (structural) {
      chart.setOption(option as echarts.EChartsCoreOption, { notMerge: true });
      return;
    }
    chart.setOption(option as echarts.EChartsCoreOption, { replaceMerge: [...DISPLAY_REPLACE] });
  }, [option, structureKey]);

  return { containerRef, chartRef };
}
