# cloudy

Enter a Swedish address (or pick a point on the map) and see **how cloudy it is**
and **how likely lightning is** near that location — per day, month, and year —
from SMHI historical open data.

## Status

**Bootstrap (2026-06-14).** The local stack runs: Postgres via Docker, FastAPI
health check, and a React app under `/app/` that confirms the API is reachable.
Ingestion, charts, Normals, predictions, deploy, and the presentation are later
milestones.

## Try it

Prereqs: Docker, [uv](https://docs.astral.sh/uv/), Node 24 + pnpm (via corepack).

```sh
cp backend/.env.example backend/.env   # optional — defaults match compose
make db && make create-db
make dev-backend    # http://localhost:8400
make dev-frontend   # second terminal — http://localhost:5273/app/
```

Health check: `curl http://localhost:8400/api/v1/health`

Also: `make test`, `make lint`, `make typecheck`.

## Repo layout

| Path | Role |
| --- | --- |
| `project.md` | Product vision, design stances, phased roadmap |
| `backend/` | FastAPI app, SQLModel, CLI (`uv run cloudy …`) |
| `frontend/app/` | Vite HTML entry for the React app at `/app/` |
| `frontend/src/` | React app source |
| `docker-compose.yml` | Local Postgres 18 |
