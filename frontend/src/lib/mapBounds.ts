import type { LightningEventPoint } from "./eventRows";

export type LngLatBounds = [[number, number], [number, number]];

/** Bounding box for maplibregl fitBounds from stroke coordinates. */
export function boundsForPoints(
  points: Pick<LightningEventPoint, "lon" | "lat">[],
  minSpanDeg = 0.12,
): LngLatBounds | null {
  if (points.length === 0) return null;

  let minLon = Infinity;
  let minLat = Infinity;
  let maxLon = -Infinity;
  let maxLat = -Infinity;

  for (const { lon, lat } of points) {
    minLon = Math.min(minLon, lon);
    minLat = Math.min(minLat, lat);
    maxLon = Math.max(maxLon, lon);
    maxLat = Math.max(maxLat, lat);
  }

  const lonSpan = Math.max(minSpanDeg, maxLon - minLon);
  const latSpan = Math.max(minSpanDeg, maxLat - minLat);
  const centerLon = (minLon + maxLon) / 2;
  const centerLat = (minLat + maxLat) / 2;

  return [
    [centerLon - lonSpan / 2, centerLat - latSpan / 2],
    [centerLon + lonSpan / 2, centerLat + latSpan / 2],
  ];
}

// Mirrors backend SWEDEN_BBOX (lightning_query.py) — bboxes outside it are 422s.
export const SWEDEN_BBOX: [number, number, number, number] = [9.0, 55.0, 26.0, 70.0];

export type ViewportBbox = [number, number, number, number]; // minLon,minLat,maxLon,maxLat

/**
 * Clamp a viewport to the API's Sweden bounds. Returns null when the viewport
 * lies entirely outside (callers fall back to the Sweden-wide query) or when
 * it covers all of Sweden anyway (bbox adds nothing over the default).
 */
export function clampViewportToSweden(viewport: ViewportBbox): ViewportBbox | null {
  const [minLon, minLat, maxLon, maxLat] = viewport;
  const [swMinLon, swMinLat, swMaxLon, swMaxLat] = SWEDEN_BBOX;
  const clamped: ViewportBbox = [
    Math.max(minLon, swMinLon),
    Math.max(minLat, swMinLat),
    Math.min(maxLon, swMaxLon),
    Math.min(maxLat, swMaxLat),
  ];
  if (clamped[0] >= clamped[2] || clamped[1] >= clamped[3]) return null;
  const coversSweden =
    clamped[0] === swMinLon && clamped[1] === swMinLat &&
    clamped[2] === swMaxLon && clamped[3] === swMaxLat;
  if (coversSweden) return null;
  return clamped.map((v) => Math.round(v * 1e4) / 1e4) as ViewportBbox; // stable query keys
}
