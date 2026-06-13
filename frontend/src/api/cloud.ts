/**
 * Cloud history API — GET /api/v1/cloud
 *
 * lat/lon resolve to the nearest active metobs param-16 station; omitted lat/lon
 * returns a Sweden-wide active-station aggregate.
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { getJson } from "./client";
import type { components } from "./schema.gen";
import type { RequestAggregation, Resolution } from "./lightning";
import { HISTORY_START, targetPointBudget, todayIso } from "./lightning";

// The per-bucket and station shapes are pure data the backend owns outright, so we
// take them straight from the generated OpenAPI schema rather than hand-mirroring.
// If the Python response model gains/renames a field, the alias shifts and any
// consumer that reads the old shape stops compiling — that's the drift guard.
// Regenerate after a backend change with `pnpm gen:api`.
export type CloudPeriod = components["schemas"]["CloudPeriod"];
export type CloudStationMeta = components["schemas"]["CloudStationMeta"];

// CloudMeta and CloudSeriesResponse stay hand-written on purpose: they refine the
// generated schema in ways the backend's plain `str` fields can't express — the
// frontend narrows `scope`/`resolved_resolution` to real unions and treats the
// planner-only fields as optional. The generated leaf aliases above carry the
// drift protection where it matters most (the data rows).
export interface CloudMeta {
  from: string;
  to: string;
  coverage_fraction: number;
  scope?: "station" | "sweden";
  station_count?: number | null;
  sources: string[];
  attribution: string;
  generated_at: string;
  total_matched?: number;
  returned?: number;
  requested_aggregation?: string;
  resolved_resolution?: Resolution;
  mode?: string;
  representation?: string;
  target_points?: number;
  point_count?: number;
  is_complete?: boolean;
}

export interface CloudSeriesResponse {
  aggregation: RequestAggregation;
  resolved_resolution: Resolution;
  station: CloudStationMeta | null;
  series: CloudPeriod[];
  meta: CloudMeta;
}

export interface CloudQueryParams {
  lat?: number;
  lon?: number;
  from?: string;
  to?: string;
  aggregation?: RequestAggregation;
  widthPx?: number;
  maxPoints?: number;
}

function buildSearchParams({
  lat,
  lon,
  from = HISTORY_START,
  to = todayIso(),
  aggregation = "auto",
  widthPx,
  maxPoints,
}: CloudQueryParams): URLSearchParams {
  const params = new URLSearchParams({
    from,
    to,
    aggregation,
  });
  if (lat !== undefined && lon !== undefined) {
    params.set("lat", String(lat));
    params.set("lon", String(lon));
  }
  if (widthPx !== undefined) params.set("width_px", String(Math.round(widthPx)));
  if (maxPoints !== undefined) params.set("max_points", String(maxPoints));
  return params;
}

export function fetchCloud(params: CloudQueryParams): Promise<CloudSeriesResponse> {
  return getJson<CloudSeriesResponse>(`/api/v1/cloud?${buildSearchParams(params).toString()}`);
}

export function useCloudSeries(
  lat: number | undefined,
  lon: number | undefined,
  from: string,
  to: string,
  aggregation: RequestAggregation,
  enabled = true,
  widthPx?: number,
) {
  const targetPoints = targetPointBudget(widthPx);
  return useQuery({
    queryKey: ["cloud", "series", lat ?? "sweden", lon ?? "sweden", from, to, aggregation, targetPoints],
    queryFn: () => fetchCloud({ lat, lon, from, to, aggregation, widthPx }),
    staleTime: 12 * 60 * 60_000,
    placeholderData: keepPreviousData,
    enabled,
  });
}
