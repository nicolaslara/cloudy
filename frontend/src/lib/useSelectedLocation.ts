import { useCallback, useEffect, useState } from "react";
import { fetchGeocode, type Candidate } from "../api/geocode";
import {
  candidateFromCoords,
  parseLocationUrl,
  writeLocationToUrl,
} from "./locationUrl";

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
