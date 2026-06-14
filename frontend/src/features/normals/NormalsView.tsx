import { useMemo, useState } from "react";
import type { Candidate } from "../../api/geocode";
import { Segmented } from "../../components/Segmented";
import { useElementWidth } from "../../lib/useElementWidth";
import {
  useCloudNormals,
  useLightningNormals,
  useSpatialNormal,
  type CloudModel,
  type CloudRadiusKm,
  type NormalsPeriod,
  type RadiusKm,
} from "./api/climatology";
import { cloudNormalsOption } from "./cloudNormalsOption";
import { lightningNormalsOption } from "./lightningNormalsOption";
import { NormalsChart } from "./NormalsChart";
import { CLOUD_LINE_KNN } from "../../lib/chartStyles";
import { CLOUD_MODEL_LABELS, spatialMonthlyMeans } from "./spatialMonthly";
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

// The point estimator overlaid on the station-normal bars: the kNN average, with its
// own line colour. The bars themselves are the "Nearest station" rung, so they aren't
// repeated as a line; the two read as one toggleable set in the legend.
const OVERLAY_MODELS: { model: CloudModel; color: string }[] = [
  { model: "knn", color: CLOUD_LINE_KNN },
];

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
  // The kNN estimate overlaid on the station bars, fetched once a place is selected.
  // The station-normal bars are the "nearest station" rung, so we only need the kNN
  // curve on top.
  const knnEstimate = useSpatialNormal(lat, lon, "knn", selected != null);

  // Fold the estimator's weekly curve to monthly and align it to the station bars'
  // months, so both sit on one axis. The curve drops out until its data lands (so the
  // bars render immediately and the line fills in), or if it has no answer here.
  const overlays = useMemo(() => {
    if (!cloud.data) return [];
    const periods = cloud.data.series.map((point) => point.period);
    const build = (result: typeof knnEstimate, model: CloudModel, color: string) => {
      if (!result.data || result.data.series.length === 0) return null;
      const monthly = spatialMonthlyMeans(result.data.series);
      return {
        name: CLOUD_MODEL_LABELS[model],
        color,
        monthly: periods.map((p) => monthly.get(p) ?? null),
      };
    };
    return OVERLAY_MODELS.map(({ model, color }) => build(knnEstimate, model, color)).filter(
      (curve): curve is NonNullable<typeof curve> => curve != null,
    );
  }, [cloud.data, knnEstimate]);

  // One cloud chart: the station-normal bars with the kNN estimate overlaid as a
  // toggleable line (legend in the chart). No location → plain bars, no overlay.
  const cloudOption = useMemo(
    () =>
      cloud.data && cloud.data.series.length > 0
        ? cloudNormalsOption(cloud.data.series, PERIOD, overlays)
        : null,
    [cloud.data, overlays],
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

  // The cloud source line reports how the station bars resolved: a regional pool when
  // several stations are in range, the lone nearest (possibly beyond the radius) when
  // the network is too sparse, or the nationwide average with no location.
  const station = cloud.data?.station;
  const stationCount = cloud.data?.station_count ?? 0;
  let sourceNote: string | null = null;
  if (!selected) {
    sourceNote = stationCount ? `Averaged across ${stationCount} stations nationwide` : null;
  } else if (station) {
    if (stationCount > 1) {
      sourceNote = `Averaged across ${stationCount} stations within ${cloudRadiusKm} km`;
    } else if (station.distance_km > cloudRadiusKm) {
      sourceNote = `Nearest station: ${station.name} (${Math.round(station.distance_km)} km — none within ${cloudRadiusKm} km)`;
    } else {
      sourceNote = `Station: ${station.name} (${Math.round(station.distance_km)} km)`;
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
            <div className="normals-controls">
              <Segmented
                label="Distance"
                options={CLOUD_RADII}
                value={cloudRadiusKm}
                onChange={setCloudRadiusKm}
                format={(option) => `${option} km`}
              />
            </div>
          )}
        </div>
        {sourceNote && <p className="normals-source">{sourceNote}</p>}
        {selected && (
          <p className="normals-source">
            Bars are the nearest-station normal; the line overlays the kNN average — the
            equal-weight mean of the nearest stations' observed normals — at your exact point. Click
            a legend entry to toggle a curve.
            {knnEstimate.isPending && " Estimating at your point…"}
          </p>
        )}
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
