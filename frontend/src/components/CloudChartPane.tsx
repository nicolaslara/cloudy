import { useMemo } from "react";
import type { CloudSeriesResponse } from "../api/cloud";
import type { Resolution } from "../api/lightning";
import { toCloudChartOption } from "../lib/cloudChartOption";
import { type VisibleZoom } from "../lib/lightningExplorer";
import { fillCloudSeries } from "../lib/cloudSeries";
import { useECharts } from "../lib/useECharts";
import { useChartZoomSync } from "../lib/useChartZoomSync";
import { queryErrorMessage } from "../lib/apiErrorMessage";

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
  const isEmpty = data !== undefined && data.series.length === 0;
  const filled = useMemo(
    () =>
      data && data.series.length > 0 ? fillCloudSeries(data.series, resolution, queryFrom, queryTo) : [],
    [data, resolution, queryFrom, queryTo],
  );
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
