import { useQuery } from "@tanstack/react-query";
import { getJson } from "./client";

// Mirrors the backend payload from GET /api/v1/health (cloudy/api/health.py).
export interface Health {
  status: "ok" | "degraded";
  db: "up" | "down";
  version: string;
}

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: () => getJson<Health>("/api/v1/health"),
    refetchInterval: 30_000,
  });
}
