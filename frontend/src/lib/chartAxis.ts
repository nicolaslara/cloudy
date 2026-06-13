type AxisExtent = { min: number; max: number };

/** Cloud cover is 0–100%; extend the axis slightly so peaks don't clip the frame. */
export const CLOUD_PERCENT_AXIS_MAX = 105;

/** ~12% headroom above the tallest bar so daily spikes don't touch the plot edge. */
export function countAxisMax(extent: AxisExtent): number {
  if (extent.max <= 0) return 1;
  const pad = Math.max(1, Math.ceil(extent.max * 0.12));
  return extent.max + pad;
}

/** Headroom for log-scaled count axes (values are log₁₀(1 + n)). */
export function logCountAxisMax(extent: AxisExtent): number {
  if (extent.max <= 0) return logAxisMaxForCount(1);
  return extent.max + Math.max(0.15, extent.max * 0.08);
}

function logAxisMaxForCount(count: number): number {
  return Math.log10(1 + count) + 0.15;
}
