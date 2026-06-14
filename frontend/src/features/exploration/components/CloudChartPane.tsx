import { useMemo } from "react";
import type { CloudSeriesResponse } from "../api/cloud";
import type { Resolution } from "../api/lightning";
import { toCloudChartOption } from "../lib/cloudChartOption";
import { type VisibleZoom } from "../lib/lightningExplorer";
import { fillCloudSeries } from "../lib/cloudSeries";
import { useECharts } from "../lib/useECharts";
import { useChartZoomSync } from "../lib/useChartZoomSync";
import { queryErrorMessage } from "../../../lib/apiErrorMessage";

// Thin renderer: it owns no fetching. The parent passes the already-fetched
// query state (data + pending/fetching/error) and a visibleZoom; this pane just
// turns that into an ECharts option, mounts it, and shows the loading/empty/
// error copy. The real work is in the lib helpers (fill, option-build, the
// chart hooks) — keeping panes interchangeable and trivial to reason about.
export function CloudChartPane({
  data,
  resolution,
  queryFrom,
  queryTo,
  visibleZoom,
  structureKey,
  stationLabel,
  isPending,
  isFetching,
  error,
  onVisibleZoom,
}: {
  data: CloudSeriesResponse | undefined;
  resolution: Resolution;
  queryFrom: string;
  queryTo: string;
  visibleZoom: VisibleZoom;
  structureKey: string;
  stationLabel: string;
  isPending: boolean;
  isFetching: boolean;
  error: Error | null;
  onVisibleZoom: (zoom: VisibleZoom) => void;
}) {
  // "Empty" = a settled response with zero rows (distinct from still-loading),
  // which is what gates the no-observations message below.
  const isEmpty = data !== undefined && data.series.length === 0;
  // Backend returns only buckets that have data; fillCloudSeries pads the gaps so
  // the x-axis is continuous and missing windows read as holes, not as a squeezed
  // axis. Memoized because option-build downstream is keyed on this array.
  const filled = useMemo(
    () =>
      data && data.series.length > 0 ? fillCloudSeries(data.series, resolution, queryFrom, queryTo) : [],
    [data, resolution, queryFrom, queryTo],
  );
  // null option = nothing to draw; the canvas is aria-hidden and the state copy
  // takes over. Rebuilds only when the filled series or grain changes.
  const option = useMemo(
    () => (filled.length > 0 ? toCloudChartOption(filled, resolution) : null),
    [filled, resolution],
  );
  const { containerRef, chartRef, lastEmittedRef } = useECharts(
    option,
    structureKey,
    onVisibleZoom,
    "chart",
    resolution,
  );
  // useECharts mounts/updates the chart and reports drags back out via
  // onVisibleZoom; useChartZoomSync pushes the parent's visibleZoom back into the
  // chart. Together they keep this pane and its sibling (slider / other charts)
  // showing the same window — lastEmittedRef breaks the echo so a drag here isn't
  // bounced back as a fresh zoom.
  const categories = useMemo(() => filled.map((point) => point.period), [filled]);
  useChartZoomSync({ chartRef, lastEmittedRef, categories, visibleZoom, resolution });

  const coveragePct = data ? Math.round(data.meta.coverage_fraction * 100) : null;
  const representation = data?.meta.representation;

  return (
    <div className="chart-area">
      <div ref={containerRef} className="chart-canvas" aria-hidden={option === null} />
      {isPending && <p className="chart-state">Loading cloud history…</p>}
      {error && (
        <p className="chart-state chart-error">
          {queryErrorMessage(error, "Could not load cloud history. Try again in a moment.")}
        </p>
      )}
      {isEmpty && (
        <p className="chart-state">
          No cloud observations for {stationLabel} in this window.
        </p>
      )}
      {coveragePct !== null && !isEmpty && (
        <p className="chart-note">
          {representation
            ? `Cloud resolved to ${resolution} buckets (${representation}). `
            : ""}
          {coveragePct}% hourly coverage in this window (station measurements may have gaps).
          {isFetching && !isPending ? " Updating…" : ""}
        </p>
      )}
    </div>
  );
}
