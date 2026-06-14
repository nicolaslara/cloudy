import { useMemo } from "react";
import type { LightningSeriesResponse, Resolution } from "../api/lightning";
import { toChartOption, type ChartScale } from "../lib/chartOption";
import { type VisibleZoom } from "../lib/lightningExplorer";
import { zeroFill } from "../lib/series";
import { useECharts } from "../lib/useECharts";
import { useChartZoomSync } from "../lib/useChartZoomSync";
import { queryErrorMessage } from "../../../lib/apiErrorMessage";

// Thin renderer, same shape as CloudChartPane: no fetching of its own — it takes
// the parent's query state and visibleZoom, builds an ECharts option, and mounts
// it via the shared chart hooks. The lightning twist is `scale` (linear vs log),
// since stroke counts span orders of magnitude across windows.
export function LightningChartPane({
  data,
  resolution,
  scale,
  fetchFrom,
  fetchTo,
  visibleZoom,
  structureKey,
  scopeLabel,
  isPending,
  error,
  onVisibleZoom,
}: {
  data: LightningSeriesResponse | undefined;
  resolution: Resolution;
  scale: ChartScale;
  fetchFrom: string;
  fetchTo: string;
  visibleZoom: VisibleZoom;
  structureKey: string;
  scopeLabel: string;
  isPending: boolean;
  error: Error | null;
  onVisibleZoom: (zoom: VisibleZoom) => void;
}) {
  const isEmpty = data !== undefined && data.series.length === 0;
  // zeroFill (not the cloud "padding" fill): missing buckets mean *zero* strokes,
  // which is real signal for lightning — a quiet week should plot a zero bar, not
  // a gap. So the fill writes explicit zeros across the queried window.
  const filled = useMemo(
    () => (data && data.series.length > 0 ? zeroFill(data.series, resolution, fetchFrom, fetchTo) : []),
    [data, resolution, fetchFrom, fetchTo],
  );
  const option = useMemo(
    () => (filled.length > 0 ? toChartOption(filled, resolution, scale) : null),
    [filled, resolution, scale],
  );
  const { containerRef, chartRef, lastEmittedRef } = useECharts(
    option,
    structureKey,
    onVisibleZoom,
    "chart",
    resolution,
  );
  const categories = useMemo(() => filled.map((point) => point.period), [filled]);
  useChartZoomSync({ chartRef, lastEmittedRef, categories, visibleZoom, resolution });

  return (
    <div className="chart-area">
      <div ref={containerRef} className="chart-canvas" aria-hidden={option === null} />
      {isPending && <p className="chart-state">Loading lightning history…</p>}
      {error && (
        <p className="chart-state chart-error">
          {queryErrorMessage(error, "Could not load lightning history. Try again in a moment.")}
        </p>
      )}
      {isEmpty && (
        <p className="chart-state">
          No lightning recorded for {scopeLabel} since 2015.
        </p>
      )}
    </div>
  );
}
