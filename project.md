# project.md — cloudy

**cloudy** is a web app that answers, for any address or picked location in
Sweden: *how cloudy is it here, historically — and how likely is lightning
nearby?* React frontend + Python backend + SQL store over SMHI open data, with
day/month/year visualizations and a prediction stack that grows from plain
climatology → non-AI statistical models → AI/ML models that must beat the
baselines.

The app surface lives under `/app/`; the root presentation page is added separately.

> This file is the **product source of truth**. When docs conflict, `project.md`
> and the design stances below win. `AGENTS.md` is the operating manual;
> `WORKING.md` is the loop; `TASKS.md` chooses the active workpad. The full
> hand-off brief (original task + modeling background + method catalog) is
> `docs/local/brief.md`.

---

## What it is

- A **location-centric climatology explorer**: type an address (or pick a point
  on a map), get charts of historical cloud cover and lightning
  probability/counts near that point, per day / month / year, plus a
  current-month expectation that updates as the month progresses.
- **Local-first.** Phase 1 is "works well locally" — real SMHI data ingested
  into a local SQL store, real charts, no deployment dependencies.
- **Benchmark-driven from day one.** Climatology is the first prediction *and*
  the permanent baseline. Every later model (statistical or AI) earns its place
  by beating it on a stated metric.

## What it is not (yet)

- Not a solar/PV production estimator. We model the weather variables (cloud,
  lightning) directly; PV output is a possible bonus later (see backlog).
- Not deployed, not multi-user, not terraform'd. Deployment is its own phase,
  entered only after the local app works well.
- Not a global weather model. AI here means **calibration, blending, and local
  correction** on top of SMHI/NWP data — never training a weather model from
  scratch.
- Not pan-Nordic in v1. Sweden first; SMHI coverage defines the boundary.

## Who it's for

Someone planning around weather at a specific Swedish place — a house, a summer
cabin, an installation site — who wants to know: which months are clear, which
are overcast, when does lightning actually strike near here, and what does the
rest of *this* month look like given what's already happened.

---

## Design stances (hard invariants)

These come from the brief and the owner's direction; they override convenience.

1. **Working end-to-end from the first milestone, one capability at a time, on
   real SMHI data.** No big-bang. The smallest first version — one location,
   one data source, one chart — beats a half-built grand architecture. Every
   milestone is demonstrable in the browser.

2. **The backend is probabilistic, source-versioned, radius-aware for
   lightning, and benchmark-driven from day one.** Predictions carry
   distributions (P10/P50/P90, calibrated probabilities), every stored value
   carries `source` + `source_version`, lightning is always defined within a
   radius (never "at the coordinate"), and every model — including the first
   AI model — must beat the climatology baseline on a stated metric before it
   serves traffic.

3. **Data-source facts are verified and dated.** SMHI APIs drift and deprecate
   (SNOW1gv1 replaced PMP3gv2; Mesan2gv3 is replacing Mesan2gv2 — see
   `docs/local/brief.md`, facts as of ~Sep 2025). Every endpoint, parameter, grid
   detail, and license we rely on is recorded with an observation date, and all
   schema knowledge for a source lives behind one ingestion boundary, so an
   API change is a one-module fix.

4. **Keep it simple and local-first.** Deployment, terraform, CI/CD, and AI
   come only after the prior phase's gate passes. Phase 1 has zero cloud
   dependencies; Phase 2 deployment stays as simple as the stack allows; AI
   waits until non-AI baselines exist to be beaten.

5. **Simplicity is a top-level rule for the code itself.** Code must always be
   easy to read and understand: good separation of concerns, one conceptual
   responsibility per file, and no oversized files (aim ~200–400 LOC per
   module; 600+ is a refactor-soon warning — see `WORKING.md`). When a clever
   solution and a boring readable one both work, the boring one wins.

6. **Treat this as a production system from day one.** Proper error handling,
   config/secrets hygiene, tests, CI, and basic
   observability are part of the first implementation (schema migrations join at the deploy phase, once there is data to preserve) — no throwaway-prototype
   shortcuts that have to be unwound later. Production-grade does **not** mean
   complex: boring, well-understood technology, the simplest thing that is
   correct and operable.

---

## Product surface

- **Input:** address search (geocoded) or direct map/coordinate pick → a selected
  stateless location filter (lat/lon + label). Selection precision can vary;
  chart APIs query by lat/lon rather than requiring saved location rows.
- **Views:** daily, monthly, and yearly charts of (a) cloud cover (mean +
  percentile band, clear/partial/overcast fractions) and (b) lightning —
  probability of any strike within R km, expected lightning days, event counts.
- **Current-month expectation:** observed-so-far + forecast + climatology tail,
  shown against the historical baseline with the revision delta.
- **Later overlays:** SNOW 10-day forecast on the charts; model confidence /
  probability bands; model-vs-baseline leaderboard.
- **API:** chart-ready JSON series per view (shapes sketched in
  `docs/local/brief.md`, ratified in the web-architecture workpad).

### Data serving and level of detail (locked 2026-06-12)

- Chart APIs stay dataset-shaped: `/api/v1/cloud` and `/api/v1/lightning`.
  There is no generic `/api/data/series` in v1.
- The public request language is `aggregation`, not legacy `granularity`.
  Normal UI controls expose only **Auto**, **Week**, **Month**, and **Year**.
  Backend `auto` may resolve internally to `raw`, `hour`, `6h`, `day`, `week`,
  `month`, or `year`.
- Backend level-of-detail selection is a semantic planner with readability
  floors plus a pixel-budget safety ceiling. Auto chooses the finest meaningful
  resolution for the visible range, but it does not show hundreds of noisy
  buckets just because the network budget allows it: very short ranges may use
  raw/hourly buckets, month-scale ranges use daily buckets, year-scale ranges
  use weekly buckets, and multi-year history uses monthly buckets unless a
  coarser manual view is selected. V1 still caps responses with
  `target_points = clamp(width_px * 1.5, 300, 3000)`.
  Do **not** downsample chart series by returning every Nth bucket, and do not
  label sampled data as complete raw data.
- Chart Auto plans against the visible query window, not the entire history
  span. The frontend keeps history navigation separate from chart payloads: a
  one-week visible window can resolve to hourly buckets, a one-month window to
  daily buckets, a one-year window to weekly buckets, and full history to
  monthly buckets, while the normal user controls still expose only
  Auto/Week/Month/Year.
- Charts have one visible time-range control: the shared bottom timeline. Chart
  canvases may keep inside zoom/pan state for synchronization, but they do not
  render a second ECharts slider. Lightning-day counts remain part of aggregate
  responses and tooltips/summaries, but they are not drawn as a daily line in
  the main unified chart.
- The backend must reject oversized requests before expensive work. Rejections
  are typed and explain the exceeded limit plus a safer aggregation where
  possible. V1 caps cloud raw responses at 3,000 points, forced raw lightning
  chart/event-row responses at 20,000 events, map dot responses at 25,000 by
  default / 50,000 maximum, and lightning scans at 5,000,000 matched events.
  The goal is never to brick the backend, degrade other users, or turn bad
  client requests into 500s.
- Cloud rollups are computed on ingest/refresh for serving resolutions and
  include mean, min, max, p05, p50, p95, observed count, missing count, and
  coverage metadata. This keeps the chart contract useful now and portable to a
  future Parquet-oriented storage path. Schema migrations backfill
  `cloud_rollups` from existing `cloud_hourly` rows so stale local databases do
  not serve empty aggregate charts after upgrade. Sweden-wide cloud is an
  aggregate across active station rollups; selected-location cloud resolves to
  the nearest station and shows the station distance.
- Lightning remains exact for arbitrary stateless lat/lon radius queries in v1:
  query raw events live with guarded preflight estimates because selected
  location queries are small. Sweden-wide chart context reads an ingest-time
  daily temporal rollup (`lightning_daily_rollups`) and re-aggregates it to
  day/week/month/year so the default interface does not scan millions of raw
  events. Do not add approximate spatial-grid lightning rollups in v1. True
  raw lightning requests over cap are rejected; map sampling is allowed only
  when the response representation says it is sampled. Map sampling is an
  explicitly incomplete visual fallback, not a chart compression strategy; v1
  uses priority sampling for representative dots rather than stride sampling.

### Deliverable vs lab: the exploration / climatology split (locked 2026-06-14)

The codebase separates the **product** from the **lab**, so the deliverable can
be presented without the heavier exploration machinery in view. Both sit on one
shared foundation.

- **Foundation (shared):** ingestion (`cloudy/ingest`), the SQL store
  (`cloudy/db`), geocoding (`cloudy/geocode`), and the source-agnostic helpers in
  `cloudy/core` (`units`, `geo`, `spatial`, `series_sql`, `cache`). Nothing in the
  foundation imports the layers above it; the two upper layers never import each
  other. The frontend mirror is `src/lib` + `src/api` + shared components, with a
  generic `useChart` so the deliverable draws charts without touching lab code.
- **Exploration (the lab):** the level-of-detail planner and the raw time-series /
  strokes / map readers — `cloudy/exploration/*` behind `/api/v1/exploration/*`,
  and `src/features/exploration/*` on the frontend. This is the data workbench
  (zoomable charts, the map, raw events); it is deliberately secondary.
- **Climatology (the deliverable, UI name "Normals"):** historical averages —
  `cloudy/climatology/*` behind `/api/v1/climatology/*`, and
  `src/features/normals/*`. "climatology" is the precise domain term (and the
  baseline every later model must beat); **"Normals"** is the user-facing label.

What the Normals product answers and how (locked 2026-06-14):

- The headline is **normal cloud cover per period** (mean % per calendar month —
  the brief's `expected_cloud_for_month`) drawn as one bar per month shaded by
  cloudiness; the clear/partly/overcast split lives in the tooltip. Lightning is
  **strike-day probability + expected lightning-days** per period within a radius.
- Period is **monthly** (the canonical normal); day-of-year and per-year slices
  stay available in the API but are not a product control. The current-month
  **live expectation** = observed-so-far + climatology tail (SNOW forecast blend
  deferred to a later phase).
- With **no location**, Normals shows the **Sweden-wide aggregate** (cloud pooled
  across all active stations; lightning across the whole country) rather than an
  empty prompt — the page always answers the question.
- **Distance filters sit beside the chart they control** and differ by data
  nature: cloud stations are sparse (~50-100 km apart) so the cloud distance pools
  stations within **50/100 km** (falling back to the single nearest when none are
  in range); lightning is dense point data, so its radius stays **10/25 km**.
- Frontend nav: **Normals** (default) and **Predictions** (roadmap, disabled) are
  the product group up top; **Exploration** and **Map** sit below in a "Lab"
  group.

---

## Core modeling definitions (distilled from `docs/local/brief.md`)

Recommended defaults, seeded from the brief — confirm in the web-architecture
workpad before they harden:

- **Time:** internal time is **UTC**; display timezone **Europe/Stockholm**.
  The daily boundary choice (UTC vs local day) is documented, not implicit.
- **Cloud:** normalized to **0–100%** everywhere. Primary metrics:
  `cloud_total_pct` (+ low/medium/high, base/top where available). Station
  oktas convert as `okta / 8 * 100`; "not observable" codes are missing, not
  >100%. Never blindly mix cloud sources (manual / ceilometer / satellite are
  not comparable) — one primary source per chart, others for validation.
- **Lightning is radius-based.** Targets are `P(any discharge within R km
  during Δt)`, counts within R, and lightning days within R. Default radius
  **10 km**, secondary **25 km** (matches SMHI thunder-day maps); 5/20 km
  supported. Never model lightning at the exact coordinate.
- **Lightning history starts 2015.** SMHI changed the lightning-localization
  calculation server in November 2014; pre/post data is not directly
  comparable, so the default historical range avoids mixing regimes.
- **Smoothed lightning-day probability:**
  `p_lightning_day = (days_with_lightning + α) / (observed_days + α + β)` with
  α = β = 1, and
  `p_any_lightning_month = 1 − (1 − p_lightning_day) ^ days_in_month`.
- **Climatology:** per-location, per-calendar-month (and day-of-year) averages
  of cloud cover and lightning days — the first prediction layer and permanent
  baseline.
- **Current-month expectation update:** weighted combination of observed hours
  so far + SNOW forecast for the next ~10 days + climatology for the remaining
  days, for both cloud and expected lightning days.
- **Provenance:** every stored observation/prediction carries `source` and
  `source_version`; large raw downloads live under gitignored `data/` paths.

### The prediction mental model (owner framing, 2026-06-10)

```text
Non-AI version:  historical observations + current SMHI forecast + statistics
                 (rules, climatology, recent-error correction, analogs,
                 explicit formulas — hand-set weights).
AI version:      the SAME data, but models learn the mapping
                 forecast/context/features → observed cloud/lightning outcome
                 (i.e. they learn the correction/blending function).
```

Non-AI comes first because it creates the baselines, data pipelines, features,
labels, and evals the AI version needs. The progression: climatology →
+ SMHI forecast → + recent-error correction → + analogs/statistical models →
AI learns the combination → calibrated ensemble blends by
horizon/location/season. Both versions share one evaluation framework and one
leaderboard; every served prediction stores its component models + weights.
Full mechanics: `docs/local/mental-model.md`.

---

## Phases (gated; see `workpads/WORKPADS.md` for the active pads)

| # | Phase | "Done" means |
| --- | --- | --- |
| 1 | **foundation** | The webapp works well **locally**: address → location mapping, historical SMHI cloud + lightning ingestion into the SQL store, daily/monthly/yearly aggregations, simple climatology predictions, and day/month/year visualizations in the browser. Stack and schema are locked via the `web-architecture` workpad gate. |
| 2 | **deploy** | The local app is deployed **simply** with basic CI/CD (GitHub Actions). Cloudflare is the candidate to research — the React-static + Python-backend split may complicate a pure-Cloudflare story; that's a research question, not a decision. Terraform is optional/nice-to-have (the original task mentions it; the owner prefers simple). |
| 3 | **non-ai-predictions** | Predictions beat raw climatology without ML: recent-residual correction, SNOW + climatology blending by horizon, analog forecasting, Poisson/negative-binomial (and zero-inflated) lightning count models, hand-weighted ensembles — all validated by rolling backtests against the climatology baseline, with a first evaluation view. |
| 4 | **ai-predictions** | The fun part, where most energy goes: gradient boosting (LightGBM-class quantile cloud models, calibrated lightning classifiers + count models) inside a calibration-and-blending architecture — feature store, model registry, rolling-origin backtests, skill scores vs the Phase-1/3 baselines, drift monitoring, explainable blends. **No AI model ships unless it beats the non-AI baselines on the right metric.** |

Sequence is gated: deploy starts only after the foundation gate; non-AI
predictions start only after the foundation gate; AI starts only after the
non-AI baselines are scored. Phase 1's gate is the product proving itself
locally.

**Foundation status (2026-06-14):** the local product is in place end-to-end —
SMHI cloud + lightning ingested, the **Normals** climatology deliverable
(monthly normals + current-month expectation, for a location or Sweden-wide)
served and rendered in the browser on real data, cleanly separated from the
exploration lab (see the split locked above). Remaining before calling the gate
done: deploy (Phase 2) and any owner-driven polish; the SNOW forecast blend in
the current-month expectation is intentionally deferred.

---

## Data sources (SMHI open data — all facts must be re-verified)

> The brief's API facts derive from SMHI announcements around **September
> 2025** and Arctic-SDI catalog records (see `docs/local/brief.md` with links).
> SNOW1gv1 replaced PMP3gv2 (PMP3gv2 deprecation was scheduled 2026-03-31);
> Mesan2gv3 replaces Mesan2gv2 (Mesan2gv2 deprecation scheduled 2026-11-01).
> **Verify current endpoint paths, parameters, grids, and licenses before any
> ingestion code** — this is the first deliverable of the `web-architecture`
> workpad. Record observation dates next to every verified fact.

- **MESAN (Mesan2gv3)** — hourly gridded meteorological analysis. Old Mesan2gv2
  grid was ~2.8 km; Mesan2gv3 uses a new grid — exact resolution unknown,
  confirm in research. Preferred historical cloud source, if enough
  history is exposed via API; open question whether deep history requires GRIB
  downloads.
- **SNOW (SNOW1gv1)** — SMHI's meteorologist-quality-controlled forecast
  database (the product is *named* SNOW — it is not snow data; it replaced the
  PMP3gv2 forecast API). ~2.5 km grid, ~10 days (≥240 h), point API takes
  arbitrary lat/lon. We use only its cloud-cover parameters and
  `thunderstorm_probability`: the forecast overlay and the current-month
  expectation.
- **Lightning archive** — historical discharge events (time, lat/lon, peak
  current, multiplicity, sensors, quality ellipse, cloud indicator). Ingest
  raw events from 2015 onward; aggregate per location/radius/window.
  Realtime-lightning availability (and whether it's restricted/paid) is a
  research item.
- **Station observations** — total cloud amount (oktas, ≥hourly for cloud
  datasets). Fallback, validation, and calibration only — not mixed into the
  primary chart series.
- **External (later, after the SMHI MVP works):** ERA5 reanalysis for longer
  climatology, ECMWF IFS/AIFS/ENS open data, CAMS, EUMETSAT satellite cloud
  products, MEPS/HARMONIE — optional upstream candidates, never Phase-1
  blockers.

Each source gets exactly one ingestion module that owns its schema knowledge,
normalization, and `source_version` stamping (stance 3).

---

## Backlog / bonus (not scheduled)

- **Terraform** for deployment — optional/nice-to-have from the original task;
  only if it stays simpler than the alternative.
- **Solar/PV output estimation** on top of the cloud model (the original
  motivation hints at it; explicitly out of base scope).
- **External data** (ERA5, ECMWF ensembles, satellite, radar nowcasting) as
  added forecast candidates and longer climatology.
- Lightning risk rings on a map; daily cloud heatmaps; "what changed since the
  last forecast" diffs; analog-years explanations; model leaderboard UI.
- **Model diagnostics endpoints** (phase 3+): `GET /models/leaderboard?target=…`
  and `GET /models/calibration?target=…` — the leaderboard/reliability data as
  first-class API surface (an impressive add-on per the owner framing).
- Multi-location compare; saved locations/sharing (post-deploy).
