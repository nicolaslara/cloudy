import { useCallback, useEffect, useState } from "react";
import { fetchGeocode, type Candidate } from "../api/geocode";
import {
  candidateFromCoords,
  parseLocationUrl,
  writeLocationToUrl,
} from "./locationUrl";

/**
 * The URL is the source of truth for the selected location, so a link is
 * shareable and back/forward navigates between locations. This hook keeps React
 * state in sync both ways: it resolves the URL into a Candidate (coords are used
 * directly; a free-text query is geocoded, taking the first Sweden match), and
 * writes the URL back whenever selection changes.
 */
export function useSelectedLocation() {
  const [selected, setSelectedState] = useState<Candidate | null>(null);
  const [resolving, setResolving] = useState(false);
  const [resolveError, setResolveError] = useState<string | null>(null);

  const applyFromUrl = useCallback(async (search: string) => {
    const parsed = parseLocationUrl(search);
    setResolveError(null);

    if (parsed.kind === "coords") {
      setSelectedState(candidateFromCoords(parsed.lat, parsed.lon));
      return;
    }

    if (parsed.kind === "query") {
      setResolving(true);
      try {
        const candidates = await fetchGeocode(parsed.query);
        const match = candidates[0];
        if (match) {
          setSelectedState(match);
          writeLocationToUrl(match);
        } else {
          setSelectedState(null);
          setResolveError(`No matches in Sweden for “${parsed.query}”.`);
        }
      } catch {
        setSelectedState(null);
        setResolveError("Could not resolve the location from the URL.");
      } finally {
        setResolving(false);
      }
      return;
    }

    setSelectedState(null);
  }, []);

  useEffect(() => {
    // Microtask: URL→state resolution must not setState synchronously in the
    // effect body (react-hooks rule; avoids cascading first-paint renders).
    queueMicrotask(() => void applyFromUrl(window.location.search));
    // Back/forward changes the URL without re-running this hook, so re-resolve
    // from location on popstate to keep state and address bar agreeing.
    const onPopState = () => void applyFromUrl(window.location.search);
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, [applyFromUrl]);

  const setSelected = useCallback((candidate: Candidate | null) => {
    setSelectedState(candidate);
    setResolveError(null);
    writeLocationToUrl(candidate);
  }, []);

  return { selected, setSelected, resolving, resolveError };
}
