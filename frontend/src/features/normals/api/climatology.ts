/**
 * Climatology API — the "Normals" feature's data layer.
 *
 * GET /api/v1/climatology/cloud and /api/v1/climatology/lightning return the
 * *typical* year for a location: historical averages with a spread band, plus a
 * live expectation for the month in progress. This module is the single seam
 * between those endpoints and the rest of the feature, mirroring the shape of
 * src/api/cloud.ts so the two read alike.
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { getJson } from "../../../api/client";
import type { components } from "../../../api/schema.gen";

// The response shapes are pure data the backend owns, so we take them straight
// from the generated OpenAPI schema rather than hand-mirroring. If a Python
// response model renames or drops a field, the alias shifts and any consumer of
// the old shape stops compiling — that's the drift guard. Regenerate after a
// backend change with `pnpm gen:api`.
export type NormalsPeriod = CloudClimatologyResponse["period"];
export type CloudNormalPoint = components["schemas"]["CloudNormalPoint"];
export type LightningNormalPoint = components["schemas"]["LightningNormalPoint"];
export type CloudClimatologyResponse = components["schemas"]["CloudClimatologyResponse"];
export type LightningClimatologyResponse =
  components["schemas"]["LightningClimatologyResponse"];
export type CloudCurrentMonth = components["schemas"]["CloudCurrentMonthExpectation"];
export type LightningCurrentMonth =
  components["schemas"]["LightningCurrentMonthExpectation"];
export type ClimatologyMeta = components["schemas"]["ClimatologyMeta"];

// Each endpoint offers two discrete radii, not a free range. They differ on
// purpose: lightning is dense point data so 10/25 km is local; cloud stations are
// ~50-100 km apart, so its distance is coarser (50 km nearest-area, 100 km a
// regional pool). Naming them makes any other value a contract mismatch.
export type RadiusKm = 10 | 25;
export type CloudRadiusKm = 50 | 100;

// lat/lon travel as a pair or not at all: with them, the normal is for the place;
// without, the backend returns the Sweden-wide aggregate. Sending only one is a
// 422, so we add both or neither.
function withLocation(
  params: URLSearchParams,
  lat: number | undefined,
  lon: number | undefined,
): URLSearchParams {
  if (lat !== undefined && lon !== undefined) {
    params.set("lat", String(lat));
    params.set("lon", String(lon));
  }
  return params;
}

function fetchCloudNormals(
  lat: number | undefined,
  lon: number | undefined,
  radiusKm: CloudRadiusKm,
  period: NormalsPeriod,
): Promise<CloudClimatologyResponse> {
  const params = withLocation(new URLSearchParams({ period }), lat, lon);
  // Radius only pools stations when there's a center; Sweden-wide ignores it.
  if (lat !== undefined && lon !== undefined) params.set("radius_km", String(radiusKm));
  return getJson<CloudClimatologyResponse>(`/api/v1/climatology/cloud?${params.toString()}`);
}

function fetchLightningNormals(
  lat: number | undefined,
  lon: number | undefined,
  radiusKm: RadiusKm,
  period: NormalsPeriod,
): Promise<LightningClimatologyResponse> {
  const params = withLocation(new URLSearchParams({ period }), lat, lon);
  // Radius only filters when there's a center; the Sweden-wide query ignores it.
  if (lat !== undefined && lon !== undefined) params.set("radius_km", String(radiusKm));
  return getJson<LightningClimatologyResponse>(
    `/api/v1/climatology/lightning?${params.toString()}`,
  );
}

// Normals are derived from years of history and don't move within a session, so
// we cache hard (12h) and keep the previous chart on screen across a period or
// location switch — a normal is a slow-moving fact, not a live feed.
const NORMALS_STALE_MS = 12 * 60 * 60_000;

export function useCloudNormals(
  lat: number | undefined,
  lon: number | undefined,
  radiusKm: CloudRadiusKm,
  period: NormalsPeriod,
  enabled = true,
) {
  return useQuery({
    queryKey: ["normals", "cloud", lat, lon, radiusKm, period],
    queryFn: () => fetchCloudNormals(lat, lon, radiusKm, period),
    staleTime: NORMALS_STALE_MS,
    placeholderData: keepPreviousData,
    // No location is a valid query now — it's the Sweden-wide normal — so this
    // always runs unless a caller explicitly disables it.
    enabled,
  });
}

export function useLightningNormals(
  lat: number | undefined,
  lon: number | undefined,
  radiusKm: RadiusKm,
  period: NormalsPeriod,
  enabled = true,
) {
  return useQuery({
    queryKey: ["normals", "lightning", lat, lon, radiusKm, period],
    queryFn: () => fetchLightningNormals(lat, lon, radiusKm, period),
    staleTime: NORMALS_STALE_MS,
    placeholderData: keepPreviousData,
    enabled,
  });
}
