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

// The spatial model's estimated week-of-year cloud normal at an arbitrary point.
// It carries a *weekly* series (ISO week 1..53) rather than the climatology's monthly
// slots, plus the nearest station and neighbour count as honest provenance for a place
// that has no station of its own.
export type SpatialNormalResponse = components["schemas"]["SpatialNormalResponse"];
export type SpatialNormalPoint = components["schemas"]["SpatialNormalPoint"];

// The cloud normal can come from two sources: the nearest-station climatology
// (today's behaviour) or an estimate at the exact point produced by a model. When
// estimating, the user also picks which model.
export type CloudSource = "station" | "estimate";
// How the week-of-year normal is estimated at a point, in increasing sophistication —
// the two rungs of one ladder, both returning the same week-of-year series so they
// read as a progression. The wire values MUST equal the backend's serve.SPATIAL_MODELS
// ("nearest" | "knn"); friendly labels live in CLOUD_MODEL_LABELS.
export type CloudModel = "nearest" | "knn";

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

// The spatial estimate is only meaningful for a concrete point (there's no
// Sweden-wide "estimate at a point"), so unlike the climatology fetchers this one
// always sends lat/lon. The model id rides as a query param so the seam grows with
// more spatial models without changing the call shape.
function fetchSpatialNormal(
  lat: number,
  lon: number,
  model: CloudModel,
): Promise<SpatialNormalResponse> {
  const params = new URLSearchParams({ lat: String(lat), lon: String(lon) });
  // The backend currently serves a single spatial model and ignores a selector, but
  // we still send it so the wire already carries the choice: the day the route reads
  // `model`, adding a spatial model is a registry change here, not a plumbing change.
  params.set("model", model);
  return getJson<SpatialNormalResponse>(`/api/v1/predictions/spatial?${params.toString()}`);
}

export function useSpatialNormal(
  lat: number | undefined,
  lon: number | undefined,
  model: CloudModel,
  enabled = true,
) {
  return useQuery({
    queryKey: ["normals", "spatial", lat, lon, model],
    // Only callable with a concrete point — the non-null assertion is guarded by
    // the `enabled` gate the caller passes (selected != null).
    queryFn: () => fetchSpatialNormal(lat!, lon!, model),
    staleTime: NORMALS_STALE_MS,
    placeholderData: keepPreviousData,
    enabled: enabled && lat !== undefined && lon !== undefined,
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
