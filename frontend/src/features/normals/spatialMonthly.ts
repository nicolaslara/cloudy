import type { CloudModel, SpatialNormalPoint } from "./api/climatology";

// The spatial model serves a *weekly* normal (ISO week 1..53), but the Normals
// view speaks in months — the climatology series, the x-axis, the current-month
// callout are all monthly. To overlay the estimate on the same chart we fold the
// weekly curve down to twelve monthly means, so both curves share one honest axis
// rather than forcing the viewer to compare a 53-slot line against a 12-slot bar.
//
// The fold maps each ISO week to a calendar month by its midpoint day and averages
// the weeks that land in each month. We anchor on a non-leap year (365 days): the
// normal is a "typical year", so the extra leap day would only shift a boundary by
// a day and never changes which month a week's centre falls in.

// ISO week w spans days [(w-1)*7 + 1 .. w*7]; its centre is (w-1)*7 + 4. Week 53
// only partly exists in most years, so its centre clamps into late December.
function weekCentreDayOfYear(week: number): number {
  return Math.min(365, (week - 1) * 7 + 4);
}

// Cumulative last-day-of-year for each month in a 365-day year. Index 0 is Jan.
const MONTH_END_DOY = [31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365];

function monthForDayOfYear(doy: number): number {
  for (let month = 0; month < MONTH_END_DOY.length; month += 1) {
    // The loop bound keeps `month` in range, so the slot is always present; the
    // `?? 365` only satisfies the no-unchecked-index check and never fires.
    if (doy <= (MONTH_END_DOY[month] ?? 365)) return month + 1; // 1-based month
  }
  return 12;
}

/**
 * Fold the spatial model's weekly cloud estimate into one mean per calendar month,
 * keyed by the same 1-based month string the climatology series uses for `period`.
 * Weeks whose estimate is null (no neighbour coverage) drop out of their month's
 * average; a month with no usable week comes back null so the line shows a gap
 * rather than inventing cover.
 */
export function spatialMonthlyMeans(
  series: SpatialNormalPoint[],
): Map<string, number | null> {
  const sums = new Map<number, { total: number; count: number }>();
  for (const point of series) {
    if (point.estimated_cloud_pct == null) continue;
    const month = monthForDayOfYear(weekCentreDayOfYear(point.week));
    const bucket = sums.get(month) ?? { total: 0, count: 0 };
    bucket.total += point.estimated_cloud_pct;
    bucket.count += 1;
    sums.set(month, bucket);
  }
  const means = new Map<string, number | null>();
  for (let month = 1; month <= 12; month += 1) {
    const bucket = sums.get(month);
    means.set(String(month), bucket && bucket.count > 0 ? bucket.total / bucket.count : null);
  }
  return means;
}

// Display names for each cloud-normal estimator, keyed by the backend's model id.
// The two rungs of one spatial ladder: the closest station, then the average of the k
// nearest. Adding a model means a member in CloudModel and an entry here — the same
// registry idiom as MODEL_LABELS in predictions.
export const CLOUD_MODEL_LABELS: Record<CloudModel, string> = {
  nearest: "Nearest station",
  knn: "Average of nearby (kNN)",
};
