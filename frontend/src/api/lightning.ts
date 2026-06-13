/**
 * Unified lightning API — GET /api/v1/lightning
 *
 * Same endpoint for chart and map; differs by `format`:
 *   - series  — aggregated buckets (bar chart)
 *   - strokes — individual events (map dots)
 *
 * Spatial filter (mutually exclusive, enforced server-side):
 *   - omit lat/lon/radius/bbox → all of Sweden
 *   - lat + lon + radius_km    → point filter (bbox derived server-side)
 *   - bbox                     → explicit window (no radius)
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { getJson } from "./client";
import type { components } from "./schema.gen";

export type Aggregation = "auto" | "week" | "month" | "year";
export type Resolution = "raw" | "hour" | "6h" | "day" | "week" | "month" | "year";
export type RequestAggregation = Aggregation | Exclude<Resolution, "week" | "month" | "year">;
export type RadiusKm = 10 | 25;
export type LightningFormat = "series" | "strokes";

export type SpatialMode = "sweden" | "bbox" | "radius";

export interface LightningSpatial {
  mode: SpatialMode;
  bbox?: [number, number, number, number];
  lat?: number;
  lon?: number;
  radius_km?: number;
}

// Pure per-bucket data the backend owns — taken straight from the generated
// OpenAPI schema so a field rename/retype on the Python side breaks compilation
// here instead of silently. The richer types below (meta, the strokes tuples,
// the narrowed request unions) stay hand-written. Regenerate with `pnpm gen:api`.
export type LightningPeriod = components["schemas"]["LightningPeriod"];

export interface LightningMeta {
  from: string;
  to: string;
  sources: string[];
  attribution: string;
  generated_at: string;
  total_matched?: number;
  returned?: number;
  downsampled?: boolean;
  stride?: number | null;
  sample_method?: string | null;
  dropped_count?: number;
  requested_aggregation?: string;
  resolved_resolution?: Resolution;
  mode?: string;
  representation?: string;
  target_points?: number;
  point_count?: number;
  is_complete?: boolean;
}

export interface LightningSeriesResponse {
  format: "series";
  aggregation: RequestAggregation;
  resolved_resolution: Resolution;
  spatial: LightningSpatial;
  series: LightningPeriod[];
  meta: LightningMeta;
}

export interface LightningStrokesResponse {
  format: "strokes";
  columns: ["lon", "lat", "peak_ka", "cg", "ts"];
  rows: [number, number, number, number, number][];
  spatial: LightningSpatial;
  meta: LightningMeta;
}

export type LightningResponse = LightningSeriesResponse | LightningStrokesResponse;

export interface LocationFilter {
  lat: number;
  lon: number;
  radiusKm: RadiusKm;
}

export const HISTORY_START = "2015-01-01";
export const DEFAULT_MAP_STROKE_POINTS = 25_000;

export function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export interface LightningQueryParams {
  from: string;
  to: string;
  format: LightningFormat;
  filter?: LocationFilter | null;
  /** Explicit viewport window — used only when no radius filter is active. */
  bbox?: [number, number, number, number] | null;
  aggregation?: Aggregation;
  widthPx?: number;
  maxPoints?: number;
  limit?: number;
}

export function targetPointBudget(widthPx?: number, maxPoints?: number): number {
  const target = Math.max(300, Math.min(Math.floor((widthPx ?? 1200) * 1.5), 3000));
  return maxPoints === undefined ? target : Math.max(1, Math.min(maxPoints, target, 3000));
}

function buildSearchParams({
  from,
  to,
  format,
  filter,
  bbox,
  aggregation = "auto",
  widthPx,
  maxPoints,
  limit = DEFAULT_MAP_STROKE_POINTS,
}: LightningQueryParams): URLSearchParams {
  const params = new URLSearchParams({ from, to, format });
  if (format === "series") {
    params.set("aggregation", aggregation);
    if (widthPx !== undefined) params.set("width_px", String(Math.round(widthPx)));
    if (maxPoints !== undefined) params.set("max_points", String(maxPoints));
  }
  if (format === "strokes") params.set("limit", String(limit));
  if (filter) {
    params.set("lat", String(filter.lat));
    params.set("lon", String(filter.lon));
    params.set("radius_km", String(filter.radiusKm));
  } else if (bbox) {
    params.set("bbox", bbox.join(","));
  }
  return params;
}

export function fetchLightning(params: LightningQueryParams): Promise<LightningResponse> {
  return getJson<LightningResponse>(`/api/v1/lightning?${buildSearchParams(params).toString()}`);
}

/** Aggregated buckets for the bar chart (`format=series`). Not used on the map. */
export function useLightningSeries(
  from: string,
  to: string,
  aggregation: Aggregation,
  filter?: LocationFilter | null,
  enabled = true,
  widthPx?: number,
) {
  const targetPoints = targetPointBudget(widthPx);
  return useQuery({
    queryKey: [
      "lightning",
      "series",
      from,
      to,
      aggregation,
      targetPoints,
      filter?.lat,
      filter?.lon,
      filter?.radiusKm,
    ],
    queryFn: async () => {
      const body = await fetchLightning({
        from,
        to,
        format: "series",
        aggregation,
        widthPx,
        filter,
      });
      if (body.format !== "series") throw new Error("expected series response");
      return body;
    },
    staleTime: 12 * 60 * 60_000,
    enabled,
  });
}

/** Individual strikes with lat/lon (`format=strokes`). One row per discharge — map only. */
export function useLightningStrokes(
  from: string,
  to: string,
  filter?: LocationFilter | null,
  limit = DEFAULT_MAP_STROKE_POINTS,
  enabled = true,
  bbox?: [number, number, number, number] | null,
) {
  return useQuery({
    queryKey: [
      "lightning",
      "strokes",
      from,
      to,
      filter?.lat,
      filter?.lon,
      filter?.radiusKm,
      bbox?.join(","),
      limit,
    ],
    queryFn: async () => {
      const body = await fetchLightning({ from, to, format: "strokes", filter, bbox, limit });
      if (body.format !== "strokes") throw new Error("expected strokes response");
      return body;
    },
    staleTime: 60 * 60_000,
    placeholderData: keepPreviousData,
    enabled,
  });
}
