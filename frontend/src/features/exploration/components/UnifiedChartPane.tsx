import { useMemo } from "react";
import type { CloudSeriesResponse } from "../api/cloud";
import type { LightningSeriesResponse, Resolution } from "../api/lightning";
import type { ChartScale } from "../lib/chartOption";
import { toUnifiedChartOption } from "../lib/unifiedChartOption";
import { type VisibleZoom } from "../lib/lightningExplorer";
import { fillCloudSeries } from "../lib/cloudSeries";
import { zeroFill } from "../lib/series";
import { useECharts } from "../lib/useECharts";
import { useChartZoomSync } from "../lib/useChartZoomSync";
import { queryErrorMessage } from "../../../lib/apiErrorMessage";

// Overlays lightning bars and the cloud curve on one shared time axis. Either
// source can be absent for a window; the other should still draw, with a note for
// the missing layer rather than a blocking empty state.
export function UnifiedChartPane({
  lightningData,
  cloudData,
  resolution,
  scale,
  fetchFrom,
  fetchTo,
  cloudQueryFrom,
  cloudQueryTo,
  visibleZoom,
  structureKey,
  scopeLabel,
  stationLabel,
  hasCloud,
  lightningPending,
  cloudPending,
  cloudFetching,
  lightningError,
  cloudError,
  onVisibleZoom,
}: {
  lightningData: LightningSeriesResponse | undefined;
  cloudData: CloudSeriesResponse | undefined;
  resolution: Resolution;
  scale: ChartScale;
  fetchFrom: string;
  fetchTo: string;
  cloudQueryFrom: string;
  cloudQueryTo: string;
  visibleZoom: VisibleZoom;
  structureKey: string;
  scopeLabel: string;
  stationLabel: string;
  hasCloud: boolean;
  lightningPending: boolean;
  cloudPending: boolean;
  cloudFetching: boolean;
  lightningError: Error | null;
  cloudError: Error | null;
  onVisibleZoom: (zoom: VisibleZoom) => void;
}) {
  const lightningEmpty = lightningData !== undefined && lightningData.series.length === 0;
  const cloudEmpty = cloudData !== undefined && cloudData.series.length === 0;
  const cloudHasRows = hasCloud && cloudData !== undefined && cloudData.series.length > 0;
  const lightningHasRows = lightningData !== undefined && lightningData.series.length > 0;

  const lightningFilled = useMemo(
    () =>
      lightningData && (lightningData.series.length > 0 || cloudHasRows)
        ? zeroFill(lightningData.series, resolution, fetchFrom, fetchTo)
        : [],
    [lightningData, cloudHasRows, resolution, fetchFrom, fetchTo],
  );
  const cloudFilled = useMemo(
    () =>
      cloudData && cloudData.series.length > 0
        ? fillCloudSeries(cloudData.series, resolution, cloudQueryFrom, cloudQueryTo)
        : [],
    [cloudData, resolution, cloudQueryFrom, cloudQueryTo],
  );

  const hasDrawableData = lightningHasRows || cloudHasRows;

  // Lightning supplies the bucket grid, but an empty lightning response is still
  // enough to make a zero-filled axis when cloud exists for the same window.
  const option = useMemo(() => {
    if (!hasDrawableData || lightningFilled.length === 0) return null;
    return toUnifiedChartOption(
      lightningFilled,
      cloudFilled,
      resolution,
      scale,
      hasCloud && cloudFilled.length > 0,
    );
  }, [hasDrawableData, lightningFilled, cloudFilled, resolution, scale, hasCloud]);

  const { containerRef, chartRef, lastEmittedRef } = useECharts(
    option,
    structureKey,
    onVisibleZoom,
    "chart",
    resolution,
  );
  const categories = useMemo(
    () => lightningFilled.map((point) => point.period),
    [lightningFilled],
  );
  useChartZoomSync({ chartRef, lastEmittedRef, categories, visibleZoom, resolution });

  // Two independent queries back one chart: it's pending while either required
  // half is loading, and lightning's error wins (cloud is supplementary — only
  // surface its error if lightning succeeded and cloud was actually requested).
  const isPending = lightningPending || (hasCloud && cloudPending);
  const error = lightningError ?? (hasCloud ? cloudError : null);
  const coveragePct = cloudData ? Math.round(cloudData.meta.coverage_fraction * 100) : null;

  return (
    <div className="chart-area">
      <div ref={containerRef} className="chart-canvas" aria-hidden={option === null} />
      {isPending && <p className="chart-state">Loading history…</p>}
      {error && (
        <p className="chart-state chart-error">
          {queryErrorMessage(error, "Could not load history. Try again in a moment.")}
        </p>
      )}
      {lightningEmpty && !isPending && !error && (
        <p className={cloudHasRows ? "chart-note" : "chart-state"}>
          {cloudEmpty
            ? `No lightning or cloud observations for ${scopeLabel} in this window.`
            : `No lightning recorded for ${scopeLabel} in this window.`}
        </p>
      )}
      {hasCloud && cloudEmpty && !lightningEmpty && !cloudPending && !cloudError && (
        <p className={lightningHasRows ? "chart-note" : "chart-state"}>
          No cloud observations for {stationLabel} in this window.
        </p>
      )}
      {hasCloud && coveragePct !== null && !cloudEmpty && (
        <p className="chart-note">
          Cloud from {stationLabel} — {coveragePct}% hourly coverage in this window.
          {cloudFetching && !cloudPending ? " Updating…" : ""}
        </p>
      )}
    </div>
  );
}
