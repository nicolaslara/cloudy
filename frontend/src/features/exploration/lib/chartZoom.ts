import type { Resolution } from "../api/lightning";

// Zoom is preserved across granularity changes by translating it through a
// resolution-independent currency: a calendar [startDay, endDay] window. We
// read the visible window off the *old* axis (readZoomRange), then snap it onto
// the *new* axis's period keys (snapRangeToCategories). Everything here is the
// glue between ECharts' axis-specific dataZoom (percent, indices, or category
// values, depending on interaction) and that stable day-string window.

export type ZoomRange = { startDay: string; endDay: string };

type DataZoomOption = {
  type?: string;
  start?: number;
  end?: number;
  startValue?: string | number;
  endValue?: string | number;
};

/** First calendar day covered by a period key. */
export function periodStartDay(period: string, resolution?: Resolution): string {
  if (resolution === "raw" || resolution === "hour" || resolution === "6h") {
    return period.slice(0, 10);
  }
  const parts = period.split("-");
  if (parts.length === 1) return `${period}-01-01`;
  if (parts.length === 2) return `${period}-01`;
  return period;
}

/** Last calendar day covered by a period key. */
export function periodEndDay(period: string, resolution?: Resolution): string {
  if (resolution === "raw" || resolution === "hour" || resolution === "6h") {
    return period.slice(0, 10);
  }
  if (resolution === "week") {
    const date = new Date(Date.parse(`${period.slice(0, 10)}T00:00:00Z`));
    date.setUTCDate(date.getUTCDate() + 6);
    return date.toISOString().slice(0, 10);
  }
  const parts = period.split("-");
  if (parts.length === 1) return `${period}-12-31`;
  if (parts.length === 2) {
    const year = Number(parts[0]);
    const month = Number(parts[1]);
    return new Date(Date.UTC(year, month, 0)).toISOString().slice(0, 10);
  }
  return period;
}

/** Normalize a dataZoom value to an ISO day string. */
export function dataZoomToDayKey(value: string | number, resolution?: Resolution): string {
  if (typeof value === "number") return new Date(value).toISOString().slice(0, 10);
  return periodStartDay(String(value), resolution);
}

export function parseUtcMs(day: string): number {
  return Date.parse(`${day}T00:00:00Z`);
}

/** The slider owns the canonical window; fall back to inside/first if absent. */
function primaryZoom(dataZoom: DataZoomOption[] | undefined): DataZoomOption | undefined {
  return (
    dataZoom?.find((zoom) => zoom.type === "slider") ??
    dataZoom?.find((zoom) => zoom.type === "inside") ??
    dataZoom?.[0]
  );
}

/** Read the visible calendar window from the active dataZoom state. */
export function readZoomRange(
  categories: string[],
  dataZoom: DataZoomOption[] | undefined,
  timeBounds?: { min: string; max: string },
  resolution?: Resolution,
): ZoomRange | null {
  const zoom = primaryZoom(dataZoom);
  if (!zoom) return null;

  // ECharts reports the window in several forms depending on axis type and how
  // the user got there: explicit start/endValue (category labels or ms), or
  // start/end percentages. Each branch below converts one form to day strings.
  // Time axis (no categories): interpolate within timeBounds.
  if (categories.length === 0 && timeBounds) {
    if (zoom.startValue != null && zoom.endValue != null) {
      return {
        startDay: dataZoomToDayKey(zoom.startValue, resolution),
        endDay: dataZoomToDayKey(zoom.endValue, resolution),
      };
    }
    if (zoom.start != null && zoom.end != null) {
      const minMs = parseUtcMs(timeBounds.min);
      const maxMs = parseUtcMs(timeBounds.max);
      const span = maxMs - minMs;
      return {
        startDay: new Date(minMs + (span * zoom.start) / 100).toISOString().slice(0, 10),
        endDay: new Date(minMs + (span * zoom.end) / 100).toISOString().slice(0, 10),
      };
    }
    return null;
  }

  if (categories.length === 0) return null;

  if (zoom.startValue != null && zoom.endValue != null) {
    const startRaw = zoom.startValue;
    const endRaw = zoom.endValue;
    // ECharts often stores category zoom as numeric indices after interaction.
    if (typeof startRaw === "number" && typeof endRaw === "number") {
      const startIdx = Math.min(categories.length - 1, Math.max(0, Math.floor(startRaw)));
      const endIdx = Math.min(categories.length - 1, Math.max(0, Math.ceil(endRaw)));
      return {
        startDay: periodStartDay(categories[startIdx]!, resolution),
        endDay: periodEndDay(categories[endIdx]!, resolution),
      };
    }
    const start = String(startRaw);
    const end = String(endRaw);
    return {
      startDay: periodStartDay(start, resolution),
      endDay: periodEndDay(end, resolution),
    };
  }

  if (zoom.start != null && zoom.end != null) {
    const last = categories.length - 1;
    const startIdx = Math.min(last, Math.max(0, Math.floor((zoom.start / 100) * last)));
    const endIdx = Math.min(last, Math.max(0, Math.ceil((zoom.end / 100) * last)));
    return {
      startDay: periodStartDay(categories[startIdx]!, resolution),
      endDay: periodEndDay(categories[endIdx]!, resolution),
    };
  }

  return null;
}

/**
 * Map a calendar window onto the nearest period keys for a new granularity axis.
 * Start snaps to the first period whose span reaches into the window, end to the
 * last period that starts before the window closes — so the rebuilt zoom covers
 * at least the same calendar range, never less. Defaults to the full axis when
 * nothing overlaps.
 */
export function snapRangeToCategories(
  range: ZoomRange,
  categories: string[],
  resolution?: Resolution,
): { startValue: string; endValue: string } {
  let startValue = categories[0]!;
  let endValue = categories[categories.length - 1]!;

  for (const period of categories) {
    if (periodEndDay(period, resolution) >= range.startDay) {
      startValue = period;
      break;
    }
  }
  for (let index = categories.length - 1; index >= 0; index -= 1) {
    const period = categories[index]!;
    if (periodStartDay(period, resolution) <= range.endDay) {
      endValue = period;
      break;
    }
  }

  return { startValue, endValue };
}

export function applyZoomRangeToDataZoom<T>(
  option: T,
  range: ZoomRange,
  categories: string[],
  resolution?: Resolution,
): T {
  const raw = (option as { dataZoom?: DataZoomOption[] | DataZoomOption }).dataZoom;
  const dataZoomList = raw == null ? [] : Array.isArray(raw) ? raw : [raw];
  if (dataZoomList.length === 0) return option;
  const { startValue, endValue } = snapRangeToCategories(range, categories, resolution);
  const dataZoom = dataZoomList.map((zoom) => {
    // Pin every zoom to the snapped category window and strip any stale
    // percentage bounds — start/end and startValue/endValue both present would
    // let ECharts pick the wrong one.
    const next = { ...zoom, startValue, endValue };
    delete next.start;
    delete next.end;
    return next;
  });
  return { ...option, dataZoom };
}
