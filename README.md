# cloudy

Enter a Swedish address (or pick a point on the map) and see **how cloudy it is**
and **how likely lightning is** near that location — per day, month, and year —
from SMHI historical open data.

## Status

**Ingestion (2026-06-13).** Postgres schema, SMHI ingest CLI, address geocoding,
and nearest cloud-station lookup work locally. Historical charts arrive in the
next milestone. The app lives at `/app/`; the root presentation page is separate.

## Try it

Prereqs: Docker, [uv](https://docs.astral.sh/uv/), Node 24 + pnpm (via corepack).

```sh
cp backend/.env.example backend/.env
make db && make migrate
make dev-backend    # http://localhost:8400
make dev-frontend   # second terminal — http://localhost:5273/app/
```

Search for a Swedish address — the header shows the resolved location and the
nearest cloud station.

Health check: `curl http://localhost:8400/api/v1/health`

### Ingest SMHI data

From `backend/` (`uv run cloudy ingest …`). Jobs are idempotent; raw downloads
land under gitignored `data/raw/`.

```sh
cd backend
uv run cloudy ingest stations
uv run cloudy ingest lightning --from 2018-07-01 --to 2018-07-31
uv run cloudy ingest cloud --station 98040
```

Also: `make test`, `make lint`, `make typecheck`.
