import { useState } from "react";
import { SearchBox } from "./components/SearchBox";
import { ViewRail } from "./components/ViewRail";
import { NormalsView } from "./features/normals";
import {
  DampedPersistenceView,
  PredictionsView,
} from "./features/predictions";
import { LightningExplorer } from "./features/exploration";
import { useStation } from "./api/station";
import { useSelectedLocation } from "./lib/useSelectedLocation";
import type { AppView } from "./lib/views";

// Honesty line under the address: cloud history isn't measured *at* the point,
// it's the nearest active station — so we name it and its distance rather than
// implying the numbers are local. A lookup failure degrades to a muted note, not
// a broken page.
function StationLine({ lat, lon }: { lat: number; lon: number }) {
  const { data: station, error } = useStation(lat, lon);
  if (error) return <p className="muted">Cloud station lookup unavailable.</p>;
  if (!station) return <p className="muted">Finding the nearest cloud station…</p>;
  return (
    <p className="muted">
      Cloud station: {station.name}, {station.distance_km} km away
    </p>
  );
}

// App shell: search + view rail + the selected-location header, wrapping whichever
// view is active. Location can arrive from the search box or a URL deep link
// (useSelectedLocation owns the ?location= resolution). Normals is the headline
// landing; the explore/map views are two presentations of the same exploration
// LightningExplorer, kept as the secondary "lab".
export function App() {
  const { selected, setSelected, resolving, resolveError } = useSelectedLocation();
  const [view, setView] = useState<AppView>("normals");

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-brand">
          <h1>cloudy</h1>
          <p className="tagline">Cloud cover and lightning history for Sweden.</p>
        </div>
        <div className="app-search">
          <SearchBox onSelect={setSelected} />
          {resolveError && <p className="search-note">{resolveError}</p>}
          {resolving && <p className="muted">Resolving location from URL…</p>}
        </div>
        {selected && (
          <div className="location-filter">
            <h2>{selected.label}</h2>
            <StationLine lat={selected.lat} lon={selected.lon} />
          </div>
        )}
      </header>

      <div className="workspace">
        <ViewRail active={view} onChange={setView} />
        <main className="workspace-main">
          {/* Normals is the headline: the typical year for the selected location. */}
          {view === "normals" && <NormalsView selected={selected} />}
          {/* Predictions: the weekly near-term outlook vs the seasonal normal. */}
          {view === "predictions" && <PredictionsView selected={selected} />}
          {/* Models: one page per prediction model — how it works + its backtest skill. */}
          {view === "damped_persistence" && <DampedPersistenceView selected={selected} />}
          {/* explore and map share one explorer, differing only in presentation —
              keeps the data wiring and zoom state in a single component. */}
          {(view === "explore" || view === "map") && (
            <LightningExplorer
              selected={selected}
              presentation={view === "map" ? "map" : "chart"}
            />
          )}
        </main>
      </div>
    </div>
  );
}
