import { useQuery } from "@tanstack/react-query";
import { getJson } from "./client";

// Mirrors GET /api/v1/station (cloudy/api/station.py).
export interface NearestStation {
  station_id: number;
  name: string;
  distance_km: number;
}

/** Nearest active cloud station — the honesty line under the charts. */
export function useStation(lat: number, lon: number) {
  return useQuery({
    queryKey: ["station", lat, lon],
    queryFn: () =>
      getJson<NearestStation>(`/api/v1/station?lat=${lat}&lon=${lon}`),
    staleTime: 12 * 60 * 60_000, // stations barely change
  });
}
