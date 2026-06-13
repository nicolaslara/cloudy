import { useStation } from "./api/station";
import { SearchBox } from "./components/SearchBox";
import { useSelectedLocation } from "./lib/useSelectedLocation";

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
  const { selected, setSelected, resolving, resolveError } = useSelectedLocation();

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
      <main className="workspace-main">
        <p className="muted">
          Search for a Swedish address to confirm geocoding and the nearest cloud
          station. Historical charts arrive in the next milestone.
        </p>
      </main>
    </div>
  );
}
