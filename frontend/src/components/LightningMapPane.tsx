import { ScatterplotLayer } from "@deck.gl/layers";
import { useDeferredValue, useMemo } from "react";
import type { LightningStrokesResponse, RadiusKm } from "../api/lightning";
import type { Candidate } from "../api/geocode";
import {
  filterByDayRange,
  parseEventRows,
  strokeColor,
  strokeTooltipHtml,
  type LightningEventPoint,
} from "../lib/eventRows";
import { boundsForPoints } from "../lib/mapBounds";
import { visibleZoomToDayRange, type VisibleZoom } from "../lib/lightningExplorer";
import { useMapDeck, type DeckTooltip } from "../lib/useMapDeck";

export function LightningMapPane({
  selected,
  radiusKm,
  visibleZoom,
  strokes,
  strokesFetching,
  strokesError,
  onUserViewport,
}: {
  selected: Candidate | null;
  radiusKm: RadiusKm;
  visibleZoom: VisibleZoom;
  strokes: LightningStrokesResponse | undefined;
  strokesFetching: boolean;
  strokesError: Error | null;
  onUserViewport?: (viewport: [number, number, number, number]) => void;
}) {
  const strokeRange = useDeferredValue(visibleZoomToDayRange(visibleZoom));

  const points = useMemo(
    () => (strokes ? parseEventRows(strokes.rows) : []),
    [strokes],
  );

  const visible = useMemo(
    () => filterByDayRange(points, strokeRange.from, strokeRange.to),
    [points, strokeRange.from, strokeRange.to],
  );

  const mapBounds = useMemo(() => boundsForPoints(visible), [visible]);

  const layers = useMemo(
    () => [
      new ScatterplotLayer({
        id: "lightning-cg",
        data: visible.filter((point) => point.cg),
        getPosition: (point) => [point.lon, point.lat],
        radiusUnits: "pixels",
        getRadius: 2.5,
        radiusMinPixels: 2.5, // generous hit target for picking
        getFillColor: (point) => strokeColor(point),
        pickable: true,
      }),
      new ScatterplotLayer({
        id: "lightning-ic",
        data: visible.filter((point) => !point.cg),
        getPosition: (point) => [point.lon, point.lat],
        radiusUnits: "pixels",
        getRadius: 2,
        filled: true,
        getFillColor: [0, 0, 0, 0], // invisible fill = pickable interior
        stroked: true,
        lineWidthMinPixels: 1,
        getLineColor: (point) => strokeColor(point),
        pickable: true,
      }),
    ],
    [visible],
  );

  // Re-fit the viewport only when the spatial context changes; a moved map
  // stays where the user put it across slider changes.
  const fitKey = selected ? `${selected.lat},${selected.lon},${radiusKm}` : "sweden";
  const getTooltip = useMemo<DeckTooltip>(
    () => (info) => {
      const point = info.object as LightningEventPoint | undefined;
      if (!point) return null;
      return {
        html: strokeTooltipHtml(point),
        style: {
          background: "rgba(22, 25, 28, 0.92)",
          color: "#e8ecf1",
          padding: "6px 9px",
          borderRadius: "6px",
          fontSize: "12px",
          lineHeight: "1.45",
        },
      };
    },
    [],
  );
  const mapRef = useMapDeck(layers, mapBounds, fitKey, getTooltip, onUserViewport);

  return (
    <>
      <div className="map-toolbar">
        {selected && (
          <span className="map-filter-note">
            Filtered to {radiusKm} km around {selected.label}
          </span>
        )}
        {strokes && !strokesFetching && (
          <span className="map-filter-note">
            {strokes.meta.downsampled
              ? `Showing ${strokes.meta.returned!.toLocaleString()} representative strokes of ${strokes.meta.total_matched!.toLocaleString()} in this window (${strokes.meta.dropped_count!.toLocaleString()} not shown)`
              : `${visible.length.toLocaleString()} strokes in this window`}
          </span>
        )}
        {strokesFetching && <span className="map-filter-note">Loading strokes…</span>}
        {!selected && (
          <span className="map-filter-note">
            {strokes?.spatial.mode === "bbox"
              ? "Strokes in the current viewport — pan/zoom to re-query"
              : "Sweden-wide individual strokes — drag the slider to change the day window"}
          </span>
        )}
      </div>
      <div className="map-stage">
        <div ref={mapRef} className="map-canvas" />
        {strokesError && <p className="map-state map-error">Could not load map data.</p>}
        {!strokesError && !strokesFetching && visible.length === 0 && (
          <p className="map-state">
            No strokes in this window{selected ? " near the selected location" : ""}.
          </p>
        )}
      </div>
    </>
  );
}
