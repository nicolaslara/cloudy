import type { LightningPeriod, Resolution } from "../api/lightning";

// Pure series transforms for the lightning chart. No React, no fetch.

const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
] as const;

/**
 * Parse any period key as a UTC instant. Bare date prefixes ("2018", "2018-07")
 * are read as the first instant of that span; an ISO string with "T" is taken
 * verbatim. Using Date.UTC (not the local Date ctor) keeps bucketing off the
 * viewer's timezone — all of our period math is UTC by contract.
 */
function parseUtc(period: string): Date {
  if (period.includes("T")) return new Date(period);
  const [y, m = 1, d = 1] = period.split("-").map(Number);
  return new Date(Date.UTC(y ?? 1970, m - 1, d));
}

function formatDay(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function formatHour(date: Date): string {
  return date.toISOString().replace(".000Z", "Z");
}

function weekStart(date: Date): Date {
  const cursor = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()));
  const day = cursor.getUTCDay() || 7;
  cursor.setUTCDate(cursor.getUTCDate() - (day - 1));
  return cursor;
}

/** All period keys between from and to (inclusive), in API period format. */
export function periodKeys(resolution: Resolution, from: string, to: string): string[] {
  const start = parseUtc(from);
  const end = parseUtc(to);
  const keys: string[] = [];
  if (resolution === "raw" || resolution === "hour") {
    const cursor = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), start.getUTCDate()));
    const last = Date.UTC(end.getUTCFullYear(), end.getUTCMonth(), end.getUTCDate(), 23);
    while (cursor.getTime() <= last) {
      keys.push(formatHour(cursor));
      cursor.setUTCHours(cursor.getUTCHours() + 1);
    }
  } else if (resolution === "6h") {
    const cursor = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), start.getUTCDate()));
    const last = Date.UTC(end.getUTCFullYear(), end.getUTCMonth(), end.getUTCDate(), 18);
    while (cursor.getTime() <= last) {
      keys.push(formatHour(cursor));
      cursor.setUTCHours(cursor.getUTCHours() + 6);
    }
  } else if (resolution === "year") {
    for (let y = start.getUTCFullYear(); y <= end.getUTCFullYear(); y += 1) {
      keys.push(String(y));
    }
  } else if (resolution === "month") {
    const cursor = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), 1));
    const last = Date.UTC(end.getUTCFullYear(), end.getUTCMonth(), 1);
    while (cursor.getTime() <= last) {
      keys.push(formatDay(cursor).slice(0, 7));
      cursor.setUTCMonth(cursor.getUTCMonth() + 1);
    }
  } else if (resolution === "week") {
    const cursor = weekStart(start);
    const last = weekStart(end).getTime();
    while (cursor.getTime() <= last) {
      keys.push(formatDay(cursor));
      cursor.setUTCDate(cursor.getUTCDate() + 7);
    }
  } else {
    const cursor = start;
    while (cursor.getTime() <= end.getTime()) {
      keys.push(formatDay(cursor));
      cursor.setUTCDate(cursor.getUTCDate() + 1);
    }
  }
  return keys;
}

const EMPTY = { cg_count: 0, all_count: 0, lightning_days: 0, max_abs_peak_ka: 0 };

/**
 * The API returns only periods with events; fill the gaps with zeros so the
 * chart axis is continuous from `from` to `to`.
 */
export function zeroFill(
  series: LightningPeriod[],
  resolution: Resolution,
  from: string,
  to: string,
): LightningPeriod[] {
  // "raw" is individual events, not a regular grid — there are no gaps to fill.
  if (resolution === "raw") return series;
  const byPeriod = new Map(series.map((point) => [point.period, point]));
  return periodKeys(resolution, from, to).map(
    (period) => byPeriod.get(period) ?? emptyLightningPeriod(period, resolution),
  );
}

function emptyLightningPeriod(period: string, resolution: Resolution): LightningPeriod {
  const start = parseUtc(period);
  const end = new Date(start);
  const hours = resolution === "6h" ? 6 : resolution === "hour" ? 1 : 24;
  end.setUTCHours(end.getUTCHours() + hours);
  return {
    period,
    bucket_start: resolution === "year" || resolution === "month" || resolution === "day" || resolution === "week"
      ? `${bucketStartDay(period)}T00:00:00Z`
      : formatHour(start),
    bucket_end: resolution === "year" || resolution === "month" || resolution === "day" || resolution === "week"
      ? `${addDays(bucketEndDay(period, resolution), 1)}T00:00:00Z`
      : formatHour(end),
    strongest_event_time: null,
    ...EMPTY,
  };
}

function bucketStartDay(period: string): string {
  if (period.length === 4) return `${period}-01-01`;
  if (period.length === 7) return `${period}-01`;
  return period.slice(0, 10);
}

function bucketEndDay(period: string, resolution: Resolution): string {
  if (resolution === "year") return `${period}-12-31`;
  if (resolution === "month") {
    const [year, month] = period.split("-").map(Number);
    return new Date(Date.UTC(year ?? 1970, month ?? 1, 0)).toISOString().slice(0, 10);
  }
  if (resolution === "week") return addDays(period.slice(0, 10), 6);
  return period.slice(0, 10);
}

function addDays(day: string, days: number): string {
  const date = parseUtc(day);
  date.setUTCDate(date.getUTCDate() + days);
  return formatDay(date);
}

/** Full human label for tooltips: "25 Jul 2018" / "Jul 2018" / "2018". */
export function periodLabel(period: string, resolution: Resolution): string {
  const date = parseUtc(period);
  const month = MONTHS[date.getUTCMonth()];
  if (resolution === "raw" || resolution === "hour" || resolution === "6h") {
    const hour = `${String(date.getUTCHours()).padStart(2, "0")}:00`;
    return `${date.getUTCDate()} ${month} ${date.getUTCFullYear()} ${hour} UTC`;
  }
  if (resolution === "year") return String(date.getUTCFullYear());
  if (resolution === "month") return `${month} ${date.getUTCFullYear()}`;
  if (resolution === "week") return `Week of ${date.getUTCDate()} ${month} ${date.getUTCFullYear()}`;
  return `${date.getUTCDate()} ${month} ${date.getUTCFullYear()}`;
}

/**
 * Compact axis tick: years as-is; months show the year only in January
 * ("Jan 2018" / "Feb"); days show the 1st of each month ("1 Jul"), blank otherwise.
 */
export function tickLabel(period: string, resolution: Resolution): string {
  const date = parseUtc(period);
  const month = MONTHS[date.getUTCMonth()] ?? "";
  if (resolution === "raw" || resolution === "hour" || resolution === "6h") {
    if (date.getUTCHours() !== 0) return "";
    return date.getUTCDate() === 1 ? `1 ${month}` : String(date.getUTCDate());
  }
  if (resolution === "year") return period;
  if (resolution === "month") {
    return date.getUTCMonth() === 0 ? `${month} ${date.getUTCFullYear()}` : month;
  }
  if (resolution === "week") {
    return date.getUTCDate() <= 7 ? `${month} ${date.getUTCFullYear()}` : String(date.getUTCDate());
  }
  return date.getUTCDate() === 1 ? `1 ${month}` : "";
}
