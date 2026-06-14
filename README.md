# cloudy

Enter a Swedish address (or pick a point on the map) and see **how cloudy it is**
and **how likely lightning is** near that location — per day, month, and year —
computed from SMHI historical open data, with progressively smarter predictions:
climatology baseline → non-AI statistical models → AI/ML models. Probabilistic,
radius-aware for lightning, and benchmark-driven from day one: every model must
beat the climatology baseline on a stated metric.

> Humans start here. Agents start at [`AGENTS.md`](./AGENTS.md).

## Status

**Foundation in progress (2026-06-11).** Local stack works: geocoding, lightning +
cloud history charts, map explorer. Postgres + SMHI ingest via `cloudy ingest`.
Climatology (Averages view) and deploy are next.

## Planned phases

1. **foundation** — webapp working well *locally*: address → location, historical
   SMHI ingestion (cloud cover + lightning), SQL store, simple climatology
   predictions, day/month/year visualizations.
2. **deploy** — only after local works: simple deployment (Cloudflare is the
   research candidate) plus basic CI/CD via GitHub Actions. Terraform is
   optional/nice-to-have.
3. **non-ai-predictions** — better predictions without AI: residual correction,
   analog forecasting, Poisson/neg-binomial lightning models, blends and
   hand-weighted ensembles, all backtested against climatology.
4. **ai-predictions** — the main event: gradient boosting + calibration +
   blending, feature store, model registry, rolling backtests, skill vs
   baselines, drift monitoring.

## Repo layout

| Path | Role |
|---|---|
| [`AGENTS.md`](./AGENTS.md) | Orchestration brain — agent entrypoint, workflow, rules |
| [`project.md`](./project.md) | Product source of truth — vision, stances, phases, data contracts |
| [`TASKS.md`](./TASKS.md) | User-edited queue; determines the active workpad |
| [`WORKING.md`](./WORKING.md) | Execution loop, gates, verification, review lenses |
| `docs/local/brief.md` | Original hand-off brief (`docs/` is entirely gitignored for now) |
| `docs/local/guide/` | HTML project guide — the local review index, kept current as the project moves |
| `workpads/` | **Gitignored** — local-only working state; durable knowledge gets promoted into `project.md` / the local guide |

## Try it

Prereqs: Docker, [uv](https://docs.astral.sh/uv/), Node 24 + pnpm (via corepack).

```sh
cp backend/.env.example backend/.env  # optional: defaults already match compose Postgres
make db                    # start Postgres 18 (docker compose, port 5432)
make migrate               # apply Alembic migrations (fresh DB: creates tables)
make dev-backend           # FastAPI on http://localhost:8400
make dev-frontend          # (second terminal) Vite on http://localhost:5273
```

Open http://localhost:5273/app//app/ — the page calls the API through the Vite dev proxy.
API docs (when `API_DOCS=true`, the default): http://localhost:8400/docs
Health check directly: `curl http://localhost:8400/api/v1/health` (reports DB
status; degrades, never crashes, when Postgres is down).

### Schema migrations (Alembic)

Schema changes are versioned with [Alembic](https://alembic.sqlalchemy.org/). Migrations
live under `backend/alembic/versions/`; models stay the source of truth in
`backend/cloudy/db/models.py`. Ingest is slow (full lightning backfill is ~70 min;
cloud is per-station), so **never reset the DB to apply a schema change** — run
migrations instead.

**Fresh database** (empty Postgres, or after `docker compose down -v`):

```sh
make db && make migrate     # cloudy migrate → alembic upgrade head
```

**Existing database** that already has tables from an older `create_all()` run (with
ingested data you want to keep)? Stamp once — records the current revision in
`alembic_version` without running any DDL:

```sh
cd backend && uv run cloudy stamp
```

**Apply pending migrations** after pulling schema changes:

```sh
make migrate                # or: cd backend && uv run cloudy migrate
```

**Add a migration** after editing `models.py`:

```sh
cd backend
uv run alembic revision --autogenerate -m "short description"
# review the generated file in alembic/versions/, then:
uv run cloudy migrate
```

Autogenerate is a draft — always read the revision before applying. `create-db` is a
deprecated alias for `migrate`.

### Ingest SMHI data manually

All ingest runs from `backend/` (`uv run cloudy ingest …`). Jobs are **idempotent**:
re-running the same day or station replaces prior rows for that unit, never duplicates.

**Raw archive (`data/raw/`, gitignored).** Every download is saved under
`data/raw/{source}/…`. If the file already exists, ingest **replays from disk** and
does not hit the network again. Resetting the database does **not** delete
`data/raw/` — only the Postgres volume.

**Reset the database** (schema + data gone; raw CSVs kept): see
[Schema migrations](#schema-migrations-alembic) — `docker compose down -v` then
`make db && make migrate`.

**Typical first-time load** (run in order; cloud needs the station registry):

```sh
cd backend

uv run cloudy ingest stations                              # ~460 stations, fast

uv run cloudy ingest lightning --from 2015-01-01 --to 2026-06-11
# full archive: ~4M events, ~4k day-files. First run downloads (<1 GB total);
# later runs replay from data/raw/smhi-lightning/ (~3 min from disk).

uv run cloudy ingest cloud --all-active
# ~109 active param-16 stations, corrected-archive backfill (2015+).
# First run downloads one CSV per station into data/raw/smhi-metobs/{id}/;
# later runs replay from disk (~5 min).
```

**One-off / incremental commands:**

```sh
cd backend

# Lightning — one day or a range
uv run cloudy ingest lightning --date 2018-07-25
uv run cloudy ingest lightning --from 2024-01-01 --to 2024-12-31

# Cloud — one station (SMHI station id, e.g. Berga = 98040) or all active
uv run cloudy ingest cloud --station 98040
uv run cloudy ingest cloud --all-active
uv run cloudy ingest cloud --station 98040 --period latest-months   # trailing ~4 months

# Stations — refresh the registry (rarely needed)
uv run cloudy ingest stations
```

Log lines show `(replay)` when reading archived raw data vs `(fetched)` on a
fresh download. Ingest progress is also recorded in the `ingest_runs` table.

Also: `make test`, `make lint`, `make typecheck`, `make fmt`, `make check-length`.
