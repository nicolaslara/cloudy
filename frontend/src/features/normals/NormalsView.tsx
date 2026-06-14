import { useMemo, useState } from "react";
import type { Candidate } from "../../api/geocode";
import { Segmented } from "../../components/Segmented";
import { useElementWidth } from "../../lib/useElementWidth";
import {
  useCloudNormals,
  useLightningNormals,
  type CloudRadiusKm,
  type NormalsPeriod,
  type RadiusKm,
} from "./api/climatology";
import { cloudNormalsOption } from "./cloudNormalsOption";
import { lightningNormalsOption } from "./lightningNormalsOption";
import { NormalsChart } from "./NormalsChart";
import {
  CloudCurrentMonthCallout,
  LightningCurrentMonthCallout,
} from "./CurrentMonthCallout";

// The normal is always the twelve-month "typical year": the monthly view is the
// product's answer to "how cloudy / how stormy is it here", and the current-month
// expectation is only meaningful monthly. Finer slices are an exploration concern.
const PERIOD: NormalsPeriod = "month";
// Two distance scales, one per data kind. Lightning is dense point data (10/25 km
// is genuinely local); cloud stations are ~50-100 km apart, so its distance pools
// a region. Each control lives next to the chart it filters.
const LIGHTNING_RADII: RadiusKm[] = [10, 25];
const CLOUD_RADII: CloudRadiusKm[] = [50, 100];

/**
 * The Normals feature: the typical year for a place — or all of Sweden when no
 * place is chosen. With no location it shows the Sweden-wide aggregate rather than
 * an empty prompt, so the page always answers the question. The two distance
 * filters sit beside the charts they affect, because cloud and lightning filter at
 * very different scales and a shared control would imply they don't.
 */
export function NormalsView({ selected }: { selected: Candidate | null }) {
  const [cloudRadiusKm, setCloudRadiusKm] = useState<CloudRadiusKm>(50);
  const [lightningRadiusKm, setLightningRadiusKm] = useState<RadiusKm>(10);
  const [containerRef] = useElementWidth<HTMLDivElement>();

  const lat = selected?.lat;
  const lon = selected?.lon;

  const cloud = useCloudNormals(lat, lon, cloudRadiusKm, PERIOD);
  const lightning = useLightningNormals(lat, lon, lightningRadiusKm, PERIOD);

  const cloudOption = useMemo(
    () =>
      cloud.data && cloud.data.series.length > 0
        ? cloudNormalsOption(cloud.data.series, PERIOD)
        : null,
    [cloud.data],
  );
  const lightningOption = useMemo(
    () =>
      lightning.data && lightning.data.series.length > 0
        ? lightningNormalsOption(lightning.data.series, PERIOD)
        : null,
    [lightning.data],
  );

  // Located vs Sweden-wide keeps the same twelve-month axis, so a switch is a data
  // change, not a structural rebuild.
  const scopeKey = selected ? "location" : "sweden";

  // The cloud source line is honest about how the radius resolved: a regional pool
  // when several stations are in range, the lone nearest (possibly beyond the
  // radius) when the network is too sparse to find any.
  const station = cloud.data?.station;
  const stationCount = cloud.data?.station_count ?? 0;
  let cloudSource: string | null = null;
  if (!selected) {
    cloudSource = stationCount ? `Averaged across ${stationCount} stations nationwide` : null;
  } else if (station) {
    if (stationCount > 1) {
      cloudSource = `Averaged across ${stationCount} stations within ${cloudRadiusKm} km`;
    } else if (station.distance_km > cloudRadiusKm) {
      cloudSource = `Nearest station: ${station.name} (${Math.round(station.distance_km)} km — none within ${cloudRadiusKm} km)`;
    } else {
      cloudSource = `Station: ${station.name} (${Math.round(station.distance_km)} km)`;
    }
  }

  return (
    <div className="normals-view" ref={containerRef}>
      <header className="normals-header">
        <h2>Typical year — {selected ? selected.label : "all of Sweden"}</h2>
      </header>

      <section className="normals-panel">
        <div className="normals-panel-head">
          <h3>Normal cloud cover</h3>
          {selected && (
            <Segmented
              label="Distance"
              options={CLOUD_RADII}
              value={cloudRadiusKm}
              onChange={setCloudRadiusKm}
              format={(option) => `${option} km`}
            />
          )}
        </div>
        {cloudSource && <p className="normals-source">{cloudSource}</p>}
        <NormalsChart
          option={cloudOption}
          structureKey={`cloud-${scopeKey}`}
          loading={cloud.isPending}
          error={cloud.error}
          empty={cloud.data !== undefined && cloud.data.series.length === 0}
          emptyMessage="No cloud normals here yet."
        />
        {cloud.data && <CloudCurrentMonthCallout data={cloud.data.current_month} />}
      </section>

      <section className="normals-panel">
        <div className="normals-panel-head">
          <h3>Lightning normals</h3>
          {selected && (
            <Segmented
              label="Radius"
              options={LIGHTNING_RADII}
              value={lightningRadiusKm}
              onChange={setLightningRadiusKm}
              format={(option) => `${option} km`}
            />
          )}
        </div>
        <p className="normals-source">
          {selected ? `Strikes within ${lightningRadiusKm} km` : "Strikes anywhere in Sweden"}
        </p>
        <NormalsChart
          option={lightningOption}
          structureKey={`lightning-${scopeKey}`}
          loading={lightning.isPending}
          error={lightning.error}
          empty={lightning.data !== undefined && lightning.data.series.length === 0}
          emptyMessage="No lightning normals here yet."
        />
        {lightning.data && (
          <LightningCurrentMonthCallout data={lightning.data.current_month} />
        )}
      </section>

      {cloud.data && (
        <footer className="normals-attribution">{cloud.data.meta.attribution}</footer>
      )}
    </div>
  );
}
