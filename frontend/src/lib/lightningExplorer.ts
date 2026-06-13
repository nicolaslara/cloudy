import type {
  Aggregation,
  LightningPeriod,
  RequestAggregation,
  Resolution,
} from "../api/lightning";
import {
  dataZoomToDayKey,
  parseUtcMs,
  periodEndDay,
  periodStartDay,
  readZoomRange,
  snapRangeToCategories,
  type ZoomRange,
} from "./chartZoom";
import { periodKeys } from "./series";

type DataZoomOption = {
  type?: string;
  start?: number;
  end?: number;
  startValue?: string | number;
  endValue?: string | number;
};

/** Visible period window on the shared time slider (matches chart axis granularity). */
export type VisibleZoom = {
  startPeriod: string;
  endPeriod: string;
};

export type LightningPresentation = "chart" | "map";

/** Width of a time-window preset (calendar span, not chart bucket size). */
export type SliderWindowPreset = "day" | "week" | "month" | "year";
export type SliderWindow = SliderWindowPreset | "custom";

const SLIDER_WINDOW_DAYS: Record<SliderWindowPreset, number> = {
  day: 1,
  week: 7,
  month: 30,
  year: 365,
};

export function isSliderWindowPreset(window: SliderWindow): window is SliderWindowPreset {
  return window !== "custom";
}

export function addCalendarDays(day: string, deltaDays: number): string {
  return new Date(parseUtcMs(day) + deltaDays * 86_400_000).toISOString().slice(0, 10);
}

export function clampDay(day: string, min: string, max: string): string {
  if (day < min) return min;
  if (day > max) return max;
  return day;
}

/**
 * When the chart asks for `auto`, the API decides the bucket size — but before
 * the first response lands we still need *some* resolution to lay out the axis
 * and snap the slider. This is that optimistic guess: an explicit aggregation is
 * already a resolution; `auto` falls back to monthly, which is the coarsest
 * common case and avoids a jarring re-snap once the real resolution arrives.
 */
export function fallbackResolution(aggregation: Aggregation): Resolution {
  return aggregation === "auto" ? "month" : aggregation;
}

/** Which panes/queries are live for a given variable×presentation cell. */
export type ExploreEnablement = {
  showUnified: boolean;
  showLightning: boolean;
  showCloud: boolean;
  /** Lightning series query gate. */
  chartEnabled: boolean;
  /** Cloud series query gate. */
  cloudEnabled: boolean;
};

/**
 * Only the chart presentation fetches series; the map fetches strokes instead.
 * Unified needs both lightning and cloud, the single-variable charts need just
 * one. Centralising this keeps the four valid cells (unified/lightning/cloud
 * charts + map) honest — every query gate flows from this one truth table.
 */
export function exploreEnablement(
  presentation: LightningPresentation,
  variable: "unified" | "lightning" | "cloud",
): ExploreEnablement {
  const showUnified = presentation === "chart" && variable === "unified";
  const showLightning = presentation === "chart" && (variable === "lightning" || showUnified);
  const showCloud = presentation === "chart" && (variable === "cloud" || showUnified);
  return {
    showUnified,
    showLightning,
    showCloud,
    chartEnabled: showLightning,
    cloudEnabled: showCloud,
  };
}

/**
 * The chart's visible window scopes the actual series query: we don't fetch all
 * of history and crop, we fetch just the days on screen (and let the API pick the
 * bucket size for that span). Both ends clamp to the fetch envelope so a slider
 * dragged past the edges can't ask for dates the backend won't serve.
 */
export function chartQueryRange(
  calendarRange: ZoomRange,
  fetchFrom: string,
  fetchTo: string,
): { from: string; to: string } {
  return {
    from: clampDay(calendarRange.startDay, fetchFrom, fetchTo),
    to: clampDay(calendarRange.endDay, fetchFrom, fetchTo),
  };
}

/**
 * On the unified chart with `auto`, the cloud series should bucket to the *same*
 * resolution the lightning query resolved to, so the two bars line up. Everywhere
 * else the cloud query just mirrors the user's chosen aggregation. The return is
 * `RequestAggregation`, not `Aggregation`: once lightning resolves `auto` to e.g.
 * `day`, that's a resolution value the narrow chart enum can't hold, but the cloud
 * endpoint accepts the wider request union.
 */
export function cloudAggregationForUnified(
  aggregation: Aggregation,
  resolvedResolution: Resolution,
  isUnified: boolean,
): RequestAggregation {
  return aggregation === "auto" && isUnified ? resolvedResolution : aggregation;
}

export function calendarRangeForWindow(
  window: SliderWindowPreset,
  anchorEndDay: string,
  fetchFrom: string,
  fetchTo: string,
): ZoomRange {
  const endDay = clampDay(anchorEndDay, fetchFrom, fetchTo);
  const spanDays = SLIDER_WINDOW_DAYS[window];
  const startDay = clampDay(addCalendarDays(endDay, -(spanDays - 1)), fetchFrom, fetchTo);
  return { startDay, endDay };
}

/** Build a visible zoom of the requested calendar width, ending on `anchorEndDay`. */
export function visibleZoomForWindow(
  window: SliderWindowPreset,
  anchorEndDay: string,
  resolution: Resolution,
  fetchFrom: string,
  fetchTo: string,
): VisibleZoom {
  return visibleZoomForCalendarRange(
    calendarRangeForWindow(window, anchorEndDay, fetchFrom, fetchTo),
    resolution,
    fetchFrom,
    fetchTo,
  );
}

export function defaultVisibleZoom(
  resolution: Resolution,
  fetchFrom: string,
  fetchTo: string,
  window: SliderWindowPreset = "year",
): VisibleZoom {
  return visibleZoomForWindow(window, fetchTo, resolution, fetchFrom, fetchTo);
}

export function visibleZoomToDayRange(
  zoom: VisibleZoom,
  resolution?: Resolution,
): { from: string; to: string } {
  return {
    from: periodStartDay(zoom.startPeriod, resolution),
    to: periodEndDay(zoom.endPeriod, resolution),
  };
}

export function visibleZoomToCalendarRange(zoom: VisibleZoom, resolution?: Resolution): ZoomRange {
  const { from, to } = visibleZoomToDayRange(zoom, resolution);
  return { startDay: from, endDay: to };
}

export function translateVisibleZoom(
  zoom: VisibleZoom,
  resolution: Resolution,
  fetchFrom: string,
  fetchTo: string,
  sourceResolution?: Resolution,
): VisibleZoom {
  return visibleZoomForCalendarRange(
    visibleZoomToCalendarRange(zoom, sourceResolution),
    resolution,
    fetchFrom,
    fetchTo,
  );
}

export function visibleZoomForCalendarRange(
  range: ZoomRange,
  resolution: Resolution,
  fetchFrom: string,
  fetchTo: string,
): VisibleZoom {
  const categories = periodKeys(resolution, fetchFrom, fetchTo);
  if (categories.length === 0) {
    return { startPeriod: range.startDay, endPeriod: range.endDay };
  }
  const { startValue, endValue } = snapRangeToCategories(
    range,
    categories,
    resolution,
  );
  return { startPeriod: startValue, endPeriod: endValue };
}

export function filterSeriesByZoom(series: LightningPeriod[], zoom: VisibleZoom): LightningPeriod[] {
  return series.filter(
    (point) => point.period >= zoom.startPeriod && point.period <= zoom.endPeriod,
  );
}

export function formatVisibleZoomLabel(zoom: VisibleZoom): string {
  const { from, to } = visibleZoomToDayRange(zoom);
  return `${from} — ${to}`;
}

/** Read the visible period window from the active dataZoom slider. */
export function readVisibleZoom(
  categories: string[],
  dataZoom: DataZoomOption[] | undefined,
  timeBounds?: { min: string; max: string },
  resolution?: Resolution,
): VisibleZoom | null {
  if (categories.length === 0 && timeBounds) {
    const slider = dataZoom?.find((zoom) => zoom.type === "slider");
    if (!slider?.startValue || !slider?.endValue) return null;
    return {
      startPeriod: dataZoomToDayKey(slider.startValue, resolution),
      endPeriod: dataZoomToDayKey(slider.endValue, resolution),
    };
  }
  const range = readZoomRange(categories, dataZoom, timeBounds, resolution);
  if (!range) return null;
  const { startValue, endValue } = snapRangeToCategories(range, categories, resolution);
  return { startPeriod: startValue, endPeriod: endValue };
}
