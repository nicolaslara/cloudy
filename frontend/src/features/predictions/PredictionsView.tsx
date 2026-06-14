import { useState } from "react";
import type { Candidate } from "../../api/geocode";
import { Segmented } from "../../components/Segmented";
import {
  useCloudBaselines,
  useLightningOutlook,
  useOutlook,
  type CloudOutlook,
  type CloudPredRadiusKm,
  type LightningOutlook,
  type LightningOutlookLead,
  type LightningPredRadiusKm,
  type OutlookLead,
  type SpatialNormalPoint,
} from "./api/predictions";

// Cloud distance pools nearby stations (they're ~50-100 km apart), same as Normals.
const CLOUD_RADII: CloudPredRadiusKm[] = [50, 100];
// Lightning is an area metric — the tighter 10/25 km of the lightning climatology.
const LIGHTNING_RADII: LightningPredRadiusKm[] = [10, 25];

// A gap of under ~2 percentage points reads as "about normal" rather than a real
// signal — below the week-to-week noise floor.
const FLAT_PP = 2;
// Lightning's noise floor: under half a lightning-day off normal isn't a signal.
const FLAT_DAYS = 0.5;

function pp(v: number | null | undefined): string {
  if (v == null) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(1)} pp`;
}

function days(v: number | null | undefined): string {
  if (v == null) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(1)} days`;
}

function leadFor(data: CloudOutlook, weeks: number): OutlookLead | undefined {
  return data.leads.find((l) => l.lead_weeks === weeks);
}

function lightningLeadFor(
  data: LightningOutlook,
  weeks: number,
): LightningOutlookLead | undefined {
  return data.leads.find((l) => l.lead_weeks === weeks);
}

function skillText(lead: OutlookLead | LightningOutlookLead | undefined): string {
  if (!lead || lead.n_origins === 0) return "n/a";
  return `${lead.skill >= 0 ? "+" : ""}${Math.round(lead.skill * 100)}%`;
}

function cloudAbs(v: number | null | undefined): string {
  return v == null ? "—" : `${Math.round(v)}%`;
}

// A cloud percentage with the "about" tilde, or an em dash when we have no estimate
// (a baseline that errored or has no normal for the target week).
function cloudTilde(v: number | null | undefined): string {
  return v == null ? "—" : `~${cloudAbs(v)}`;
}

function daysAbs(v: number | null | undefined): string {
  return v == null ? "—" : v.toFixed(1);
}

// Read a point's seasonal normal for a specific ISO week from a spatial series.
function normalAt(series: SpatialNormalPoint[] | undefined, week: number): number | null {
  if (!series) return null;
  return series.find((p) => p.week === week)?.estimated_cloud_pct ?? null;
}

// The damped prediction on a given baseline normal: the normal nudged by the
// persisted recent anomaly, clamped to a real cloud percentage.
function dampedOn(normal: number | null, anomalyPct: number | null | undefined): number | null {
  if (normal == null || anomalyPct == null) return null;
  return Math.max(0, Math.min(100, normal + anomalyPct));
}

/**
 * The cloud outlook as a *progression* (shown when a point is selected): the same
 * prediction, built up from plain statistics so the reader sees exactly what each
 * layer adds.
 *
 * Two axes interleave. The seasonal normal — "what a typical week of the year looks
 * like" — can be pinned to the point two increasingly precise ways: the nearest
 * station, then the average of the k nearest (kNN). Damped persistence is the
 * orthogonal *time* step: it nudges either of those normals by how far recent weeks
 * ran off normal, since that gap tends to persist. The table crosses the two for next
 * week.
 */
function CloudProgression({
  data,
  baselines,
  place,
}: {
  data: CloudOutlook;
  baselines: ReturnType<typeof useCloudBaselines>;
  place: string;
}) {
  const recent = data.recent_anomaly_pct;
  const lead1 = leadFor(data, 1);
  const lead2 = leadFor(data, 2);
  if (recent == null || !lead1) {
    return (
      <p className="predictions-outlook-text">
        Not enough recent cloud observations {place} to form an outlook yet.
      </p>
    );
  }

  // The damped lead names its ISO week, so the point's week-of-year normal lines up
  // with the week the anomaly is carried into. The table details next week (lead 1).
  const week = lead1.target_week;
  const anomaly = lead1.expected_anomaly_pct;
  const rows = [
    { key: "nearest", label: "Nearest station", data: baselines.nearest.data },
    { key: "knn", label: "Average of nearby (kNN)", data: baselines.knn.data },
  ].map((r) => {
    const normal = normalAt(r.data?.series, week);
    return { ...r, normal, damped: dampedOn(normal, anomaly) };
  });

  const anyPending = baselines.nearest.isPending || baselines.knn.isPending;
  const k = baselines.knn.data?.n_neighbours ?? 5;
  const station = baselines.nearest.data?.nearest_station;

  return (
    <div className="predictions-outlook">
      {/* Headline stays the deployed, backtested model: the radius-pooled normal +
          damped. The table below shows the point-precise variants. */}
      <p className="predictions-outlook-lead">
        Expected cloud cover {place}: <strong>~{cloudAbs(lead1.expected_cloud_pct)}</strong> next
        week and <strong>~{cloudAbs(lead2?.expected_cloud_pct)}</strong> the week after.
      </p>
      <p className="predictions-outlook-text">
        How that prediction sharpens for next week — from the nearest station to the kNN average
        {station ? ` (nearest station ${station.name}, ${Math.round(station.distance_km)} km)` : ""}:
      </p>
      <table className="predictions-progression">
        <thead>
          <tr>
            <th scope="col">Estimate at your point</th>
            <th scope="col">Seasonal normal</th>
            <th scope="col">+ damped persistence</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key}>
              <th scope="row">{r.label}</th>
              <td>{cloudTilde(r.normal)}</td>
              <td>{cloudTilde(r.damped)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {anyPending && <p className="normals-source">Estimating at your point…</p>}
      <p className="predictions-outlook-text">
        <strong>Seasonal normal</strong> is the typical cloud for this week of the year — just
        statistics, estimated at your point two ways: the nearest station, then the average of the{" "}
        {k} nearest (kNN), a sharper read of the same point.{" "}
        <strong>Damped persistence</strong> then nudges it by how far recent weeks have run off
        normal (now <strong>{pp(recent)}</strong>), since that gap tends to persist. Backtested
        skill of the damped step vs the normal: {skillText(lead1)} at 1 week, {skillText(lead2)} at
        2 weeks.
      </p>
    </div>
  );
}

/**
 * The near-term outlook stated in words — the model's real edge.
 *
 * Recent weeks ran some amount off the seasonal normal; weekly anomalies persist,
 * so the next week or two are expected to run a damped fraction of that gap off
 * normal. We say exactly that, with the backtested skill so the reader knows how
 * much to trust it. No chart on purpose: it's a sentence, not a figure.
 */
function OutlookStatement({ data, place }: { data: CloudOutlook; place: string }) {
  const recent = data.recent_anomaly_pct;
  if (recent == null) {
    return (
      <p className="predictions-outlook-text">
        Not enough recent cloud observations {place} to form an outlook yet.
      </p>
    );
  }

  const lead1 = leadFor(data, 1);
  const lead2 = leadFor(data, 2);
  const aboutNormal = Math.abs(recent) < FLAT_PP;
  const direction = recent >= 0 ? "cloudier than" : "clearer than";
  const thin = (lead1?.n_origins ?? 0) < 52;

  return (
    <div className="predictions-outlook">
      {/* Lead with the actual prediction — the absolute % — not just the gap. */}
      <p className="predictions-outlook-lead">
        Expected cloud cover {place}: <strong>~{cloudAbs(lead1?.expected_cloud_pct)}</strong> next
        week and <strong>~{cloudAbs(lead2?.expected_cloud_pct)}</strong> the week after.
      </p>
      <p className="predictions-outlook-text">
        {aboutNormal ? (
          <>
            That tracks the seasonal normal — recent weeks have run about normal (now ~
            {cloudAbs(data.recent_cloud_pct)}, {pp(recent)}).
          </>
        ) : (
          <>
            Recent weeks ran {direction} normal (now ~{cloudAbs(data.recent_cloud_pct)},{" "}
            <strong>{pp(recent)}</strong>); that gap tends to persist, leaving the next two weeks
            about <strong>{pp(lead1?.expected_anomaly_pct)}</strong> /{" "}
            <strong>{pp(lead2?.expected_anomaly_pct)}</strong> off the seasonal normal.
          </>
        )}
      </p>
      <p className="predictions-outlook-skill">
        Backtested skill vs climatology: {skillText(lead1)} at 1 week, {skillText(lead2)} at 2 weeks
        {thin ? " — thin history, treat with caution" : ""}.
      </p>
    </div>
  );
}

/**
 * The lightning outlook — the same damped model, hedged for sparsity.
 *
 * Lightning is counted in weekly lightning-days and the series trails the calendar
 * out of season, so we name the week it's `as_of` and lean on the caveat: a weekly
 * strike count is bursty, so this is the indicative second line under the cloud
 * headline, not a confident forecast.
 */
function LightningStatement({ data, place }: { data: LightningOutlook; place: string }) {
  const recent = data.recent_anomaly_days;
  if (recent == null) {
    return (
      <p className="predictions-outlook-text">
        Not enough lightning history {place} to form an outlook.
      </p>
    );
  }

  const lead1 = lightningLeadFor(data, 1);
  const lead2 = lightningLeadFor(data, 2);
  const direction = recent >= 0 ? "more active than" : "quieter than";
  const aboutNormal = Math.abs(recent) < FLAT_DAYS;
  const asOf = data.as_of_week ? `the week of ${data.as_of_week}` : "the latest week";

  return (
    <div className="predictions-outlook">
      {/* Lead with the actual expected lightning-day count, not just the gap. */}
      <p className="predictions-outlook-lead">
        Expected lightning {place}: <strong>~{daysAbs(lead1?.expected_lightning_days)}</strong>{" "}
        days next week and <strong>~{daysAbs(lead2?.expected_lightning_days)}</strong> the week
        after{data.radius_km ? ` (within ${data.radius_km} km)` : ""}.
      </p>
      <p className="predictions-outlook-text">
        {aboutNormal
          ? `About the seasonal normal — ${asOf} ran ~${daysAbs(data.recent_lightning_days)} lightning-days, about typical.`
          : `${asOf} ran ${direction} normal (~${daysAbs(data.recent_lightning_days)} lightning-days, ${days(recent)}); that gap tends to persist into the next weeks.`}
      </p>
      <p className="predictions-outlook-skill">
        Backtested skill vs climatology: {skillText(lead1)} at 1 week, {skillText(lead2)} at 2 weeks
        — lightning is sparse and bursty, so treat this as indicative.
      </p>
    </div>
  );
}

/**
 * The Predictions tab: a weekly near-term cloud outlook, stated in plain words.
 * Damped anomaly persistence is faithful-but-flat at monthly leads, but at WEEKLY
 * resolution it genuinely beats the seasonal normal — so that's what we show, as a
 * sentence with its backtested skill rather than a busy chart. No location → the
 * Sweden-wide outlook.
 */
export function PredictionsView({ selected }: { selected: Candidate | null }) {
  const [cloudRadiusKm, setCloudRadiusKm] = useState<CloudPredRadiusKm>(50);
  const [lightningRadiusKm, setLightningRadiusKm] = useState<LightningPredRadiusKm>(25);

  const outlook = useOutlook(selected?.lat, selected?.lon, cloudRadiusKm);
  const lightning = useLightningOutlook(selected?.lat, selected?.lon, lightningRadiusKm);
  // The point-precise normals (nearest -> kNN) behind the progression; only fetched
  // for a concrete point, so they're idle on the Sweden-wide view.
  const baselines = useCloudBaselines(selected?.lat, selected?.lon);
  const place = selected ? `near ${selected.label}` : "across Sweden";

  return (
    <div className="normals-view predictions-view">
      <header className="normals-header">
        <h2>Near-term outlook — {selected ? selected.label : "all of Sweden"}</h2>
        <p className="predictions-intro">
          A weekly outlook for cloud cover and lightning: recent weather, nudged forward by how
          much it tends to persist. The baseline it's measured against is the seasonal normal.
        </p>
      </header>

      <section className="normals-panel">
        <div className="normals-panel-head">
          <h3>Next two weeks</h3>
          {selected && (
            <Segmented
              label="Distance"
              options={CLOUD_RADII}
              value={cloudRadiusKm}
              onChange={setCloudRadiusKm}
              format={(o) => `${o} km`}
            />
          )}
        </div>
        {outlook.isPending && <p className="normals-source">Loading outlook…</p>}
        {outlook.error && (
          <p className="normals-source chart-error">Could not load the outlook. Try again in a moment.</p>
        )}
        {/* A selected point gets the full progression (normal three ways -> damped);
            Sweden-wide has no point estimate, so it keeps the plain statement. */}
        {outlook.data &&
          (selected ? (
            <CloudProgression data={outlook.data} baselines={baselines} place={place} />
          ) : (
            <OutlookStatement data={outlook.data} place={place} />
          ))}
      </section>

      <section className="normals-panel">
        <div className="normals-panel-head">
          <h3>Lightning</h3>
          {selected && (
            <Segmented
              label="Distance"
              options={LIGHTNING_RADII}
              value={lightningRadiusKm}
              onChange={setLightningRadiusKm}
              format={(o) => `${o} km`}
            />
          )}
        </div>
        {lightning.isPending && <p className="normals-source">Loading outlook…</p>}
        {lightning.error && (
          <p className="normals-source chart-error">Could not load the outlook. Try again in a moment.</p>
        )}
        {lightning.data && <LightningStatement data={lightning.data} place={place} />}
        {selected && (
          <p className="normals-source">
            No point-precise (kNN) lightning estimate yet — lightning is counted over an area, not
            interpolated between stations, so the spatial progression above is cloud-only for now.
          </p>
        )}
      </section>

      {outlook.data && (
        <footer className="normals-attribution">{outlook.data.meta.attribution}</footer>
      )}
    </div>
  );
}
