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

// Overlays lightning bars and the cloud curve on one shared time axis. Lightning
// is the spine: the x-axis categories come from the lightning series, and if
// there's no lightning to draw there's no chart at all (the cloud-only case
// falls back to copy). Cloud is layered in only when present and `hasCloud`.
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

  const lightningFilled = useMemo(
    () =>
      lightningData && lightningData.series.length > 0
        ? zeroFill(lightningData.series, resolution, fetchFrom, fetchTo)
        : [],
    [lightningData, resolution, fetchFrom, fetchTo],
  );
  const cloudFilled = useMemo(
    () =>
      cloudData && cloudData.series.length > 0
        ? fillCloudSeries(cloudData.series, resolution, cloudQueryFrom, cloudQueryTo)
        : [],
    [cloudData, resolution, cloudQueryFrom, cloudQueryTo],
  );

  // Lightning drives the axis: with no lightning points there's nothing to anchor
  // the cloud curve against, so we bail to null (state copy) even if cloud exists.
  const option = useMemo(() => {
    if (lightningFilled.length === 0) return null;
    return toUnifiedChartOption(
      lightningFilled,
      cloudFilled,
      resolution,
      scale,
      hasCloud && cloudFilled.length > 0,
    );
  }, [lightningFilled, cloudFilled, resolution, scale, hasCloud]);

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
      {lightningEmpty && (
        <p className="chart-state">
          No lightning recorded for {scopeLabel} since 2015.
        </p>
      )}
      {hasCloud && cloudEmpty && !cloudPending && !cloudError && (
        <p className="chart-note">
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
