import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { getJson } from "./client";

// Mirrors cloudy/api/geocode.py.
export interface Candidate {
  label: string;
  lat: number;
  lon: number;
  provider: string;
}

/** One-shot geocode for URL `?location=` deep links. */
export function fetchGeocode(query: string): Promise<Candidate[]> {
  return getJson<Candidate[]>(`/api/v1/geocode?q=${encodeURIComponent(query.trim())}`);
}

/** Debounced address suggestions: min 3 chars, 300 ms — the Photon politeness lever. */
export function useGeocode(input: string) {
  const [query, setQuery] = useState("");

  useEffect(() => {
    // Debounce keystrokes into a single committed `query`: each new input cancels
    // the pending timer, so we only fire a request once typing pauses for 300 ms.
    // The <3-char floor clears the query (stops short, noisy lookups), and the
    // cleanup guarantees no in-flight timer outlives the latest keystroke.
    const trimmed = input.trim();
    const handle = setTimeout(() => setQuery(trimmed.length >= 3 ? trimmed : ""), 300);
    return () => clearTimeout(handle);
  }, [input]);

  return useQuery({
    queryKey: ["geocode", query],
    queryFn: () => fetchGeocode(query),
    enabled: query.length >= 3,
    staleTime: 5 * 60_000,
  });
}
