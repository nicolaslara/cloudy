import { useState } from "react";
import { SearchBox } from "./components/SearchBox";
import { LightningExplorer } from "./components/LightningExplorer";
import { ViewRail } from "./components/ViewRail";
import { useHealth } from "./api/health";
import { useStation } from "./api/station";
import { useSelectedLocation } from "./lib/useSelectedLocation";
import type { AppView } from "./lib/views";

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

export function App() {
  const { data: health, error } = useHealth();
  const healthState = error ? "unreachable" : (health?.status ?? "checking");
  const { selected, setSelected, resolving, resolveError } = useSelectedLocation();
  const [view, setView] = useState<AppView>("explore");

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
          {(view === "explore" || view === "map") && (
            <LightningExplorer
              selected={selected}
              presentation={view === "map" ? "map" : "chart"}
            />
          )}
          {view === "averages" && (
            <p className="workspace-hint">Monthly climatology averages — coming after cloud history.</p>
          )}
          {view === "predictions" && (
            <p className="workspace-hint">Predictions layer — gated on non-AI baselines.</p>
          )}
        </main>
      </div>

      <footer className="footer">
        <span className={`dot dot-${healthState}`} aria-label={`backend ${healthState}`} />
        backend: {healthState}
      </footer>
    </div>
  );
}
