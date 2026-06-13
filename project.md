# project.md — cloudy

**cloudy** is a web app that answers, for any address or picked location in
Sweden: *how cloudy is it here, historically — and how likely is lightning
nearby?* React frontend + Python backend + SQL store over SMHI open data, with
day/month/year visualizations and a prediction stack that grows from plain
climatology to statistical models that must beat the baseline.

The app surface lives under `/app/`. The root presentation page is a separate
artifact and is not part of the product commits.

---

## What it is

- A **location-centric climatology explorer**: type an address, get charts of
  historical cloud cover and lightning near that point, per day / month / year.
- **Local-first.** The first milestones prove the product on a developer laptop
  with real SMHI data — no cloud dependencies until deploy.
- **Benchmark-driven.** Climatology is the first prediction layer and the
  permanent baseline. Every later model must beat it before it ships.

## Design stances

1. **Working end-to-end from the first milestone**, one capability at a time.
2. **Probabilistic, source-versioned, radius-aware for lightning.** Lightning is
   always within a radius, never at the exact coordinate.
3. **Data-source facts are verified and dated.** Each source gets one ingestion
   module so API drift is contained.
4. **Keep it simple and local-first.** Deploy and models follow the local product.
5. **Readable code.** One responsibility per file; split before modules get large.
6. **Production habits from day one** — error handling, tests, CI, config hygiene.

---

## Phases

| # | Phase | Done means |
| --- | --- | --- |
| 1 | **foundation** | Address → location, SMHI ingestion, SQL store, exploration charts, Normals climatology — all working locally. |
| 2 | **predictions** | Damped persistence outlook scored against climatology on a rolling backtest. |
| 3 | **deploy** | Neon Postgres, Fly.io API, Cloudflare Pages, and Terraform scaffold. |

**Current status (2026-06-14):** scaffold landed — FastAPI + React + Postgres
health check. Ingestion and charts are next.

---

## Core defaults

- Internal time **UTC**; display **Europe/Stockholm**.
- Cloud cover **0–100%**; station oktas convert as `okta / 8 * 100`.
- Lightning within **10 km** by default; history from **2015** onward.
- Every stored value carries `source` and `source_version`.
