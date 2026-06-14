import { useDeferredValue, useMemo } from "react";
import type { Candidate } from "../../../api/geocode";
import { useCloudSeries } from "../api/cloud";
import {
  DEFAULT_MAP_STROKE_POINTS,
  useLightningSeries,
  useLightningStrokes,
  type Aggregation,
  type LocationFilter,
  type RadiusKm,
} from "../api/lightning";
import type { ViewportBbox } from "./mapBounds";
import {
  chartQueryRange,
  cloudAggregationForUnified,
  exploreEnablement,
  fallbackResolution,
  visibleZoomToDayRange,
  type LightningPresentation,
  type VisibleZoom,
} from "./lightningExplorer";

// "month" is deliberately both a valid Aggregation (what useLightningSeries asks
// for) and a Resolution (how the slider lays out its axis), so keep it a literal
// rather than widening to Resolution — that lets it satisfy both call sites.
const TIME_SLIDER_RESOLUTION = "month" as const;

function toFilter(selected: Candidate | null, radiusKm: RadiusKm): LocationFilter | null {
  if (!selected) return null;
  return { lat: selected.lat, lon: selected.lon, radiusKm };
}

/**
 * All of LightningExplorer's data wiring lives here: the four queries (chart
 * series, cloud series, map strokes, and the always-on month slider) plus the
 * window-scoped range derivation that feeds them. The component only ever drove
 * these from state, never from each other's data — except for one real coupling:
 * the cloud query's bucket size depends on the lightning query's *resolved*
 * resolution on the unified chart. That dependency is the reason this is a hook
 * and not a pure function — it has to read one query's response to shape the next.
 *
 * Every query is gated off the same enablement truth table (`exploreEnablement`)
 * so the four valid cells stay honest: chart fetches series, map fetches strokes,
 * unified fetches both, and nothing fetches what its cell won't render.
 */
export function useLightningExploreData({
  selected,
  presentation,
  variable,
  aggregation,
  radiusKm,
  calendarRange,
  visibleZoom,
  viewportBbox,
  chartWidth,
  fetchFrom,
  fetchTo,
}: {
  selected: Candidate | null;
  presentation: LightningPresentation;
  variable: "unified" | "lightning" | "cloud";
  aggregation: Aggregation;
  radiusKm: RadiusKm;
  /** Deferred calendar range — the visible window that scopes the series query. */
  calendarRange: { startDay: string; endDay: string };
  visibleZoom: VisibleZoom;
  viewportBbox: ViewportBbox | null;
  chartWidth: number | undefined;
  fetchFrom: string;
  fetchTo: string;
}) {
  const filter = toFilter(selected, radiusKm);
  const { showUnified, showLightning, showCloud, chartEnabled, cloudEnabled } =
    exploreEnablement(presentation, variable);

  const { from: chartQueryFrom, to: chartQueryTo } = chartQueryRange(
    calendarRange,
    fetchFrom,
    fetchTo,
  );

  const lightning = useLightningSeries(
    chartQueryFrom,
    chartQueryTo,
    aggregation,
    filter,
    chartEnabled,
    chartWidth,
  );
  const chartResolution = lightning.data?.resolved_resolution ?? fallbackResolution(aggregation);
  const cloudAggregation = cloudAggregationForUnified(aggregation, chartResolution, showUnified);

  // Cloud reuses the lightning chart's day window verbatim — same span, same edges.
  const cloudRange = useMemo(
    () => ({ from: chartQueryFrom, to: chartQueryTo }),
    [chartQueryFrom, chartQueryTo],
  );
  const cloud = useCloudSeries(
    selected?.lat,
    selected?.lon,
    cloudRange.from,
    cloudRange.to,
    cloudAggregation,
    cloudEnabled,
    chartWidth,
  );
  const cloudResolution = cloud.data?.resolved_resolution ?? chartResolution;

  // The slider always loads a coarse month series for the whole envelope so the
  // overview track is populated regardless of the chart's zoomed-in window.
  const monthSlider = useLightningSeries(
    fetchFrom,
    fetchTo,
    TIME_SLIDER_RESOLUTION,
    filter,
    presentation === "map" || presentation === "chart",
    chartWidth,
  );

  // The map loads individual strikes for just the days the slider exposes; on the
  // map the slider speaks month buckets, so translate the zoom through "month".
  const strokeRange = useDeferredValue(
    visibleZoomToDayRange(visibleZoom, presentation === "map" ? "month" : chartResolution),
  );
  const strokes = useLightningStrokes(
    strokeRange.from,
    strokeRange.to,
    filter,
    DEFAULT_MAP_STROKE_POINTS,
    presentation === "map",
    filter ? null : viewportBbox,
  );

  return {
    filter,
    showUnified,
    showLightning,
    showCloud,
    timeSliderResolution: TIME_SLIDER_RESOLUTION,
    chartQueryFrom,
    chartQueryTo,
    chartResolution,
    cloudRange,
    cloudResolution,
    lightning,
    cloud,
    monthSlider,
    strokes,
  };
}
