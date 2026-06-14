import { MapboxOverlay } from "@deck.gl/mapbox";
import type { Layer, PickingInfo } from "@deck.gl/core";
import maplibregl from "maplibre-gl";
import { useEffect, useRef } from "react";
import type { LngLatBounds } from "./mapBounds";
import "maplibre-gl/dist/maplibre-gl.css";

const DARK_STYLE = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";
const SWEDEN_CENTER: [number, number] = [16.5, 62.4];

export type DeckTooltip = (info: PickingInfo) => { html: string; style?: object } | null;

// fitBounds is a no-op before the style loads, so defer the fit to the "load"
// event when the map isn't ready yet. The follow-up resize() works around
// MapLibre mis-sizing when the container's dimensions settle after init.
function fitWhenReady(map: maplibregl.Map, bounds: LngLatBounds) {
  const apply = () =>
    map.fitBounds(bounds, { padding: 56, maxZoom: 11, duration: 480, essential: true });
  if (map.loaded()) {
    apply();
    requestAnimationFrame(() => map.resize());
  } else {
    map.once("load", () => {
      apply();
      requestAnimationFrame(() => map.resize());
    });
  }
}

/**
 * MapLibre map with a deck.gl overlay; layers swap without remounting the map.
 *
 * Auto-fit policy: fit to `bounds` when `fitKey` changes (a new spatial
 * context — location/radius), and never after the user has panned or zoomed
 * within the current context. Slider/data changes keep the user's viewport.
 */
export function useMapDeck(
  layers: Layer[],
  bounds: LngLatBounds | null,
  fitKey = "",
  getTooltip?: DeckTooltip,
  onUserViewport?: (viewport: [number, number, number, number]) => void,
) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const overlayRef = useRef<MapboxOverlay | null>(null);
  const userMovedRef = useRef(false);
  const lastFitKeyRef = useRef<string | null>(null);
  const onUserViewportRef = useRef(onUserViewport);
  useEffect(() => {
    onUserViewportRef.current = onUserViewport;
  });

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const map = new maplibregl.Map({
      container,
      style: DARK_STYLE,
      center: SWEDEN_CENTER,
      zoom: 4.2,
      attributionControl: {},
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

    // Programmatic fits emit moveend without originalEvent; user gestures carry one.
    const onMoveEnd = (event: { originalEvent?: unknown }) => {
      if (!event.originalEvent) return;
      userMovedRef.current = true;
      const b = map.getBounds();
      onUserViewportRef.current?.([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()]);
    };
    map.on("moveend", onMoveEnd);

    const overlay = new MapboxOverlay({ interleaved: true, layers });
    map.addControl(overlay as unknown as maplibregl.IControl);
    mapRef.current = map;
    overlayRef.current = overlay;

    const observer = new ResizeObserver(() => map.resize());
    observer.observe(container);
    requestAnimationFrame(() => map.resize());

    return () => {
      observer.disconnect();
      map.off("moveend", onMoveEnd);
      overlay.finalize();
      map.remove();
      mapRef.current = null;
      overlayRef.current = null;
      lastFitKeyRef.current = null;
    };
    // Mount-once: `layers` is read here only to seed the overlay; live updates
    // go through the setProps effect below, so re-running this on every layer
    // change would needlessly tear down and rebuild the whole map. Hence the
    // intentional exhaustive-deps warning — do not "fix" it by adding `layers`.
  }, []);

  // Push new layers/tooltip onto the existing overlay without remounting the map.
  useEffect(() => {
    overlayRef.current?.setProps({ layers, getTooltip });
  }, [layers, getTooltip]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !bounds) return;
    const contextChanged = lastFitKeyRef.current !== fitKey;
    if (contextChanged) {
      lastFitKeyRef.current = fitKey;
      userMovedRef.current = false; // new context: auto-fit is welcome again
      fitWhenReady(map, bounds);
      return;
    }
    if (!userMovedRef.current) {
      fitWhenReady(map, bounds); // untouched map follows the data window
    }
  }, [bounds, fitKey]);

  return containerRef;
}
