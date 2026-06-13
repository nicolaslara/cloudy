import type { Candidate } from "../api/geocode";

/** Rough Sweden bounding box — rejects coordinates outside the product area. */
const SWEDEN = { latMin: 55.0, latMax: 69.1, lonMin: 10.0, lonMax: 24.2 };

export type ParsedLocationUrl =
  | { kind: "coords"; lat: number; lon: number }
  | { kind: "query"; query: string }
  | { kind: "none" };

export function isInSweden(lat: number, lon: number): boolean {
  return (
    lat >= SWEDEN.latMin &&
    lat <= SWEDEN.latMax &&
    lon >= SWEDEN.lonMin &&
    lon <= SWEDEN.lonMax
  );
}

function parseLatLng(raw: string): { lat: number; lon: number } | null {
  const parts = raw.split(",").map((part) => part.trim());
  if (parts.length !== 2) return null;
  const lat = Number(parts[0]);
  const lon = Number(parts[1]);
  if (!Number.isFinite(lat) || !Number.isFinite(lon) || !isInSweden(lat, lon)) return null;
  return { lat, lon };
}

/**
 * Parse `?latlng=` or `?location=` — never both. If both are set they are
 * ignored (no guarantee they match).
 */
export function parseLocationUrl(search: string): ParsedLocationUrl {
  const params = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
  const latlng = params.get("latlng")?.trim();
  const location = params.get("location")?.trim();

  if (latlng && location) {
    console.warn("cloudy: URL has both location= and latlng=; ignoring both.");
    return { kind: "none" };
  }

  if (latlng) {
    const coords = parseLatLng(latlng);
    if (coords) return { kind: "coords", ...coords };
  }

  if (location && location.length >= 3) {
    return { kind: "query", query: location };
  }

  return { kind: "none" };
}

export function formatCoords(lat: number, lon: number): string {
  return `${lat},${lon}`;
}

export function coordLabel(lat: number, lon: number): string {
  return `${lat.toFixed(3)}°, ${lon.toFixed(3)}°`;
}

export function candidateFromCoords(lat: number, lon: number, provider = "url"): Candidate {
  return {
    label: coordLabel(lat, lon),
    lat,
    lon,
    provider,
  };
}

/** Write one param: latlng for direct coordinates, location for geocoded labels. */
export function writeLocationToUrl(candidate: Candidate | null): void {
  const url = new URL(window.location.href);
  url.searchParams.delete("location");
  url.searchParams.delete("latlng");

  if (candidate) {
    if (candidate.provider === "url") {
      url.searchParams.set("latlng", formatCoords(candidate.lat, candidate.lon));
    } else {
      url.searchParams.set("location", candidate.label);
    }
  }

  const next = `${url.pathname}${url.search}${url.hash}`;
  if (`${window.location.pathname}${window.location.search}${window.location.hash}` !== next) {
    window.history.replaceState(null, "", next);
  }
}
