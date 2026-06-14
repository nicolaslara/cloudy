/**
 * Predictions API — the weekly near-term outlooks + the static leaderboard.
 *
 * Outlook endpoints (GET /api/v1/predictions/outlook for damped cloud,
 * /lightning-outlook for lightning) plus the
 * read-only /backtest leaderboard. lat/lon travel together or not at all (without
 * them, the backend returns the Sweden-wide outlook). Types are derived from the
 * generated schema so a backend rename breaks compilation here rather than
 * silently producing stale data. Regenerate with `pnpm gen:api`.
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { getJson } from "../../../api/client";
import type { components } from "../../../api/schema.gen";

export type CloudOutlook = components["schemas"]["CloudOutlook"];
export type OutlookLead = components["schemas"]["OutlookLead"];
export type LightningOutlook = components["schemas"]["LightningOutlook"];
export type LightningOutlookLead = components["schemas"]["LightningOutlookLead"];
export type BacktestArtifact = components["schemas"]["BacktestArtifact"];
export type ModelScores = components["schemas"]["ModelScores"];
export type SpatialNormalResponse = components["schemas"]["SpatialNormalResponse"];
export type SpatialNormalPoint = components["schemas"]["SpatialNormalPoint"];
export type BacktestSeriesResponse = components["schemas"]["BacktestSeriesResponse"];
export type BacktestSeriesPoint = components["schemas"]["BacktestSeriesPoint"];
// The two ways to estimate a point's week-of-year cloud normal, sharpest last —
// the rungs of one spatial ladder. Wire values match the backend's serve.SPATIAL_MODELS.
export type CloudBaselineModel = "nearest" | "knn";
// The model ids that key the backtest leaderboard — must match the backend's
// BacktestModels fields. Adding a model is a field there and an entry here.
export type ModelId = keyof BacktestArtifact["models"];

// Cloud distance pools nearby stations (they're ~50-100 km apart), same as Normals.
export type CloudPredRadiusKm = 50 | 100;
// Lightning is an area metric, so its radii are the tighter 10/25 km of the
// lightning climatology; the outlook defaults to the wider 25 km for sample.
export type LightningPredRadiusKm = 10 | 25;

function fetchOutlook(
  lat: number | undefined,
  lon: number | undefined,
  radiusKm: CloudPredRadiusKm,
): Promise<CloudOutlook> {
  const params = new URLSearchParams();
  // Both or neither: a lone coordinate is a 422, and no coords means Sweden-wide.
  if (lat !== undefined && lon !== undefined) {
    params.set("lat", String(lat));
    params.set("lon", String(lon));
    params.set("radius_km", String(radiusKm));
  }
  return getJson<CloudOutlook>(`/api/v1/predictions/outlook?${params.toString()}`);
}

// The outlook is derived from years of history and only moves with new data, so a
// 12h cache is right; keeping the previous text on screen across a location switch
// avoids a flicker while the new fetch lands.
const OUTLOOK_STALE_MS = 12 * 60 * 60_000;

export function useOutlook(
  lat: number | undefined,
  lon: number | undefined,
  radiusKm: CloudPredRadiusKm,
  enabled = true,
) {
  return useQuery({
    queryKey: ["predictions", "outlook", lat, lon, radiusKm],
    queryFn: () => fetchOutlook(lat, lon, radiusKm),
    staleTime: OUTLOOK_STALE_MS,
    placeholderData: keepPreviousData,
    enabled,
  });
}

function fetchLightningOutlook(
  lat: number | undefined,
  lon: number | undefined,
  radiusKm: LightningPredRadiusKm,
): Promise<LightningOutlook> {
  const params = new URLSearchParams();
  if (lat !== undefined && lon !== undefined) {
    params.set("lat", String(lat));
    params.set("lon", String(lon));
    params.set("radius_km", String(radiusKm));
  }
  return getJson<LightningOutlook>(`/api/v1/predictions/lightning-outlook?${params.toString()}`);
}

export function useLightningOutlook(
  lat: number | undefined,
  lon: number | undefined,
  radiusKm: LightningPredRadiusKm,
  enabled = true,
) {
  return useQuery({
    queryKey: ["predictions", "lightning-outlook", lat, lon, radiusKm],
    queryFn: () => fetchLightningOutlook(lat, lon, radiusKm),
    staleTime: OUTLOOK_STALE_MS,
    placeholderData: keepPreviousData,
    enabled,
  });
}

// One point's week-of-year cloud normal, estimated `model` ways. Both rungs
// (nearest/knn) are station observations and always answer; we don't retry-storm and
// let the caller degrade a missing row gracefully.
function fetchSpatialNormal(
  lat: number,
  lon: number,
  model: CloudBaselineModel,
): Promise<SpatialNormalResponse> {
  const params = new URLSearchParams({ lat: String(lat), lon: String(lon), model });
  return getJson<SpatialNormalResponse>(`/api/v1/predictions/spatial?${params.toString()}`);
}

function useSpatialBaseline(
  lat: number | undefined,
  lon: number | undefined,
  model: CloudBaselineModel,
) {
  return useQuery({
    queryKey: ["predictions", "spatial", lat, lon, model],
    queryFn: () => fetchSpatialNormal(lat!, lon!, model),
    staleTime: OUTLOOK_STALE_MS,
    placeholderData: keepPreviousData,
    retry: false,
    enabled: lat !== undefined && lon !== undefined,
  });
}

/**
 * The point-precise cloud-normal estimates behind the outlook, fetched together so
 * the Predictions view can show the progression nearest → kNN. Only meaningful for a
 * concrete point (there's no Sweden-wide point estimate), so both are gated on
 * lat/lon being present.
 */
export function useCloudBaselines(lat: number | undefined, lon: number | undefined) {
  return {
    nearest: useSpatialBaseline(lat, lon, "nearest"),
    knn: useSpatialBaseline(lat, lon, "knn"),
  };
}

// One model's forecast-vs-actual over its rolling-origin backtest at a point. Both
// coords or neither (Sweden-wide). The lead is the horizon; model picks the forward
// model. Like the outlook, it only moves with new data, so it caches hard.
function fetchBacktestSeries(
  lat: number | undefined,
  lon: number | undefined,
  radiusKm: CloudPredRadiusKm,
  model: ModelId,
  lead: 1 | 2,
): Promise<BacktestSeriesResponse> {
  const params = new URLSearchParams({ model, lead: String(lead) });
  if (lat !== undefined && lon !== undefined) {
    params.set("lat", String(lat));
    params.set("lon", String(lon));
    params.set("radius_km", String(radiusKm));
  }
  return getJson<BacktestSeriesResponse>(
    `/api/v1/predictions/backtest-series?${params.toString()}`,
  );
}

export function useBacktestSeries(
  lat: number | undefined,
  lon: number | undefined,
  radiusKm: CloudPredRadiusKm,
  model: ModelId,
  lead: 1 | 2,
  enabled = true,
) {
  return useQuery({
    queryKey: ["predictions", "backtest-series", lat, lon, radiusKm, model, lead],
    queryFn: () => fetchBacktestSeries(lat, lon, radiusKm, model, lead),
    staleTime: OUTLOOK_STALE_MS,
    placeholderData: keepPreviousData,
    enabled,
  });
}

// The static cross-station benchmark — the same for everyone, fetched once. A 503
// means it hasn't been evaluated yet (`cloudy backtest`), so don't retry-storm.
function fetchBacktest(): Promise<BacktestArtifact> {
  return getJson<BacktestArtifact>("/api/v1/predictions/backtest");
}

export function useBacktest(enabled = true) {
  return useQuery({
    queryKey: ["predictions", "backtest"],
    queryFn: fetchBacktest,
    staleTime: OUTLOOK_STALE_MS,
    retry: false,
    enabled,
  });
}
